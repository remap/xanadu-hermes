import jinja2
from types import SimpleNamespace
import tempfile
import os
import logging
from pathlib import Path
import pathlib
import json
import re
from jsonmerge import merge
from pprint import pprint
import time
import asyncio
from watchfiles import awatch, Change
from hermes.utils import jformat
from pprint import pprint
import boto3
from datetime import datetime
from hermes.ch.media import convert_exr_to_png
import mimetypes

mimetypes.add_type("image/x-exr", ".exr")
from hermes.ch.collection import UploadableCollection
from hermes.ch.aws import SQSNotifier, SQSListener

import jsonpickle


class PosixPathHandler(jsonpickle.handlers.BaseHandler):
    def flatten(self, obj, data):
        return str(obj)


jsonpickle.handlers.register(pathlib.PosixPath, PosixPathHandler)


# class UploadableCollectionHandler(jsonpickle.handlers.BaseHandler):
#     def flatten(self, obj, data):
#         return obj.to_summary()
# jsonpickle.handlers.register(UploadableCollection, UploadableCollectionHandler)
#

def to_namespace(d):
    return SimpleNamespace(**{k: to_namespace(v) if isinstance(v, dict) else v for k, v in d.items()})


TIME_STRING_FORMAT = "%Y-%m-%dT%H:%M:%S"
log_file_watch_detail = False

uc_status_init = {
    "phase": "initialized",
    "last_notify": "",
    "failure": False,
    "msg_detail": "",
    "outputs" : []
}


## REFACTOR STATUS TO SIT INSIDE THE UPLOADABLE COLLECITON
## and add other states
##

## output-dir:  while to put stuff

## GenAIModuleRemote implements the logic to gather files and upload them to a remote AI processing module
## Right now, a few things, like EXR => PNG conversion when needed, are baked in
## But trying to do what we can in Jinja templates
##

class GenAIModuleRemote:
    # self.config and self.dynamic are module-wide vars
    # to override for writing a specific metadata, pass overrides into metadata  template

    listener = None
    monitor_task = None

    def __init__(self, s3, sqs, sns, config_file: str, config_common_file: str = None, base_dir='.', firebase = None, logger=None):
        # Get AWS clients from above so we don't have to control credentials here
        self.s3 = s3
        self.sqs = sqs
        self.sns = sns
        #
        self.base_dir = Path(base_dir)
        self.config_file = Path(config_file)
        self.config_dir = self.config_file.parent
        self.config_common_file = Path(config_common_file)
        self.DEBOUNCE_SEC = 1
        self.uploadable_collections = {}
        self.uploadable_collections_status = {}
        self.dynamic_vars = {}  # dict version
        self.dynamic = None  # Becomes simplenamespace of dynamic_vars
        self.firebase = firebase


        # Read config files
        ## config_common_file :  Common configuration file across all modules(optional), which can be overridden
        ## config file:  module-specific config
        ##
        if self.config_common_file is not None:
            try:
                with open(self.config_common_file) as f:
                    config_str = f.read()
                self._config_dict = json.loads(config_str)
            except json.JSONDecodeError as e:
                self.logger.error(f"GenAIModuleRemote: Invalid JSON in config file {self.config_file} - {e}")
                raise
        else:
            self._config_dict = {}
        try:
            with open(self.config_file) as f:
                config_str = f.read()
            self._config_dict = merge(self._config_dict, json.loads(config_str))
        except json.JSONDecodeError as e:
            self.logger.error(f"GenAIModuleRemote: Invalid JSON in config file {self.config_file} - {e}")
            raise
        self.config = to_namespace(self._config_dict)

        # Now that we've loaded the name, set up logger
        self.name = self.config.module



        class PrefixAdapter(logging.LoggerAdapter):
            def process(self, msg, kwargs):
                module = self.extra.get("module", "")
                return f"{module}: {msg}", kwargs

        self.logger = PrefixAdapter(logger or logging.getLogger(__name__), {"module": self.name})

        self.output_dir = self.base_dir / Path(self.config.metadata.output_dir)
        self.watch_dir = None  # filled in when watching


        # firebase
        self.notify_key = "/".join([self.config.firebase.notify_key, self.name])
        self.logger.info(f"Firebase notify {self.notify_key}")
        self.logger.debug(f"Deleting firebase key {self.notify_key}")
        self.firebase.delete_async(self.config.firebase.notify_key, self.name)

        ## Setup SQS notifier callback for end of inference
        self.notifier = SQSNotifier(self.sqs, self.sns, self.config.sqs.notify_queue_name,
                                    self.config.s3.input_bucket, self.config.pipeline.name, self.config.module,
                                    self.config.pipeline.start_phase, self.logger)

        ## Listen for incoming events.
        if GenAIModuleRemote.listener is None:
            GenAIModuleRemote.listener = SQSListener(self.sqs, self.sns, self.config.sqs.listen_queue_name,
                                                     self.config.sns.listen_topic_arn, self.logger)

        GenAIModuleRemote.listener.add_callback(self.name, self.listen_callback)


    def to_summary(self):
        s = {}
        s["name"] = self.name
        uc = {}
        # TODO: Refactor status
        for key, value in self.uploadable_collections.items():
            uc[str(key)] = value.to_summary()
            uc[str(key)].update(
                self.uploadable_collections_status[key])  # Key is posix path but we use string in outgoing summary
        s["uploadable_collections"] = uc
        return s

    def to_json(self):
        return jsonpickle.encode(self.to_summary(), unpicklable=False)

    # TODO: refactor to use a specific unique identifier
    #
    def get_unique_id(self, m):
        arn = m["metadata_arn"]
        f = arn.split("/")[-1]
        p = f.replace("-metadata.json", "")
        return p

    def get_collection_key(self, p):
        c = self.get_unique_id(p)
        return Path("/".join(c.split("-")[:3]))  # key is posix path

    # File downloading
    #
    def listen_callback(self, msg):

        if msg.get("module", "") != self.config.module:  # TODO: Let die silently?
            return
        try:
            key = self.get_collection_key(msg)
        except Exception as e:
            key = ""
        if key in self.uploadable_collections_status:
            t = datetime.now().strftime(TIME_STRING_FORMAT)
            # print(f"*** updating {key} with {t}")
            self.uploadable_collections_status[key]["last_notify"] = t
            self.uploadable_collections_status[key]["msg_detail"] = msg
            self.uploadable_collections_status[key]["phase"] = msg.get("phase")
        if msg.get("status", "") == "failure":
            s = f"Failure: \n{msg.get('error_code')} {msg.get('error_message')}\n {msg.get('exceptions')} \n{msg}"
            self.logger.error(s)
            if key in self.uploadable_collections_status:
                self.uploadable_collections_status[key]["failure"] = True
            if self.firebase is not None:
                result = self.firebase.post_async("/".join([self.notify_key, str(key)]),
                                                  {"timestamp": datetime.now().strftime(TIME_STRING_FORMAT),
                                                   "status": "failure",
                                                   "files": {}}, params={'print': 'pretty'},
                                                  headers={'X_FANCY_HEADER': 'VERY FANCY'},
                                                  callback=lambda result: self.logger.info(
                                                      f"firebase post of failure to {self.config.firebase.notify_key} for {key}"))
            return
        if "next_metadata" not in msg:
            self.logger.error(f"Incoming message had no next_metadata: {msg}")
            return
        msg["next_metadata"] = json.loads(msg["next_metadata"])
        # If Postprocess, download the file
        #
        if msg.get("phase") != "postprocess":  # download after the postprocess phase is complete
            return
        self.logger.info(f"{self.name} callback received postprocess message: \n{jformat(msg)}")

        if key not in self.uploadable_collections_status:
            self.logger.error(f"The key {key} is not a pending collection. Download aborted.")
            return

        # TODO: Template this?
        # Directory structure is instance/module/output/ and we write group/user/trial/
        try:
            output_dir = self.output_dir / msg["next_metadata"]["group"] / msg["next_metadata"]["user"] / \
                         msg["next_metadata"]["trial"]
        except Exception as e:
            output_dir = self.output_dir / "error"
            self.logger.error(f"Error constructing output path, using {output_dir}")
        try:
            self.logger.debug(f"creating if necessary {output_dir}")
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Error creating directory '{output_dir}': {e}", exc_info=True)

        new_loop = asyncio.new_event_loop()
        tasks = list()
        # TODO: Hacky for metadata
        arns = msg.get("media_arns") | {"metadata.json": msg.get("metadata_arn")}  #list(msg.get("media_arns").values())
        #arns.append(msg.get("metadata_arn"))
        for filekey, arn in arns.items():  # ToDo: name collision possibility, at least theoretically
            try:
                resource = arn.split(":", 5)[-1]
                bucket, s3key = resource.split('/', 1)
            except Exception as e:
                raise ValueError(f"Invalid S3 ARN: {arn}") from e
            file_path = Path(s3key)
            metadata = msg.get("next_metadata")
            collection_key = Path("/".join([metadata["group"],metadata["user"], metadata["trial"]])) # Gotta fix this use of path
            tasks.append(new_loop.create_task(self.download_from_s3(bucket, s3key, filekey, output_dir / file_path.name, collection_key)))

        gather_future = asyncio.gather(*tasks)
        gather_future.add_done_callback(lambda fut: self.download_complete(fut, key ))
        new_loop.run_until_complete(gather_future)
        new_loop.close()

    def download_complete(self, future, collection_key):
        files = {}
        for f in future.result():
            for k,v in f.items():
                files[k.replace(".","_")] = v   # firebase doesn't support periods in keys.
        self.logger.info(f"COMPLETE for {collection_key} results: {json.dumps(files)}")
        if self.firebase is not None:
            result = self.firebase.post_async("/".join([self.notify_key,str(collection_key)]), {"timestamp": datetime.now().strftime(TIME_STRING_FORMAT), "status" : "success", "files" : files },
                                         callback=lambda result: self.logger.debug(f"firebase post to {self.config.firebase.notify_key} for {collection_key}"))




    async def download_from_s3(self, bucket, s3key, filekey, file_path: Path,collection_key, notifier=None) -> None:
        file_path = Path(file_path)
        filename = file_path.name  # os.path.basename(file_path)
        self.logger.debug(f"Downloading {s3key} from bucket {bucket} to {file_path} ...")
        try:
            await asyncio.to_thread(self.s3.download_file, bucket, s3key, file_path)
            self.logger.info(f"Downloaded {s3key} from bucket {bucket} to {file_path.resolve().as_uri()} successfully.")

            self.uploadable_collections_status[collection_key]["outputs"].append(file_path.resolve().as_uri())
        except Exception as err:
            self.logger.error(f"Error downloading {s3key} from bucket {bucket} to {file_path.resolve()}: {err}", exc_info=True)
            return None
        return {filekey : str(file_path.resolve())}

    def load_dynamic(self, dynamic_vars: dict, merge=False):
        if merge:
            self.dynamic_vars = self.dynamic_vars | dynamic_vars
        else:
            self.dynamic_vars = dynamic_vars
        self.dynamic = to_namespace(self.dynamic_vars)
        self._extra_vars = self.dynamic_vars

    def render_template(self, template_path=None, overrides={}):
        if template_path is None: template_path = self.config_dir / self.config.metadata.template_file
        try:
            with open(template_path) as f:
                tmpl = f.read()
            template = jinja2.Template(tmpl)
            context = {"config": self.config, **(self._extra_vars | overrides), "dynamic": self.dynamic}
            rendered = template.render(context)
            return json.loads(rendered)
        except json.JSONDecodeError as e:
            self.logger.error(f"Error decoding JSON from rendered template {template_path}: {e}")
            raise

    def write_template(self, template_path=None):
        rendered = self.render_template(template_path)
        try:
            output_file = rendered.get("metadata_file")
            if not output_file:
                self.logger.error(f"No 'metadata_file' key in rendered template")
                raise ValueError("Missing 'metadata_file' key in rendered template")
            output_path = self.output_dir / output_file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(rendered, f, indent=2)
            return output_path
        except Exception as e:
            self.logger.error(f"Error writing rendered template to '{output_path}': {e}", exc_info=True)
            raise

    # called by uploadable collection
    def metadatawriter(self, metadata_file, media_files):
        self.logger.debug(f"Metadatawriter: metadata_file: {metadata_file}, media_files: {media_files}")
        overrides = {
            "metadata_local_path": str(metadata_file["path"].parent),
            "metadata_file": metadata_file["s3_unique_name"],
            "media_files": [{'name': f['s3_unique_name'], 'mimetype': f['mimetype']} for f in media_files.values()],
            "timestamp": datetime.now().strftime(TIME_STRING_FORMAT)
        }
        return json.dumps(self.render_template(overrides=overrides), indent=4)

    def fileactions(self, filepath):
        file = Path(filepath)
        mime_type, encoding = mimetypes.guess_type(filepath)
        self.logger.debug(f"fileactions: {mime_type}, {encoding}, {file}")
        if mime_type == "image/x-exr":
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(convert_exr_to_png(file, file.with_suffix(".png")))
            except Exception as e:
                self.logger.error(f"Error creating async task in fileactions {e}", exc_info=True)

    def path_ends_with(self, full_path: Path, ending: Path) -> bool:
        ending_parts = ending.parts
        full_parts = full_path.parts
        # print(full_path,ending)
        if len(ending_parts) > len(full_parts):
            return False
        return full_parts[-len(ending_parts):] == ending_parts

    async def manage_create(self, rel_path: Path, file_path: Path) -> None:
        try:
            if file_path.is_dir():
                if rel_path in self.uploadable_collections:
                    self.logger.warn(f"Skipping creation of UploadableCollection '{rel_path}', already seen")
                else:
                    ## TODO: Fix - merge with logic below
                    depth = len(rel_path.parts)
                    if depth >= self.config.ue.require_depth:
                        self.logger.info(f"Creating UploadableCollection '{rel_path}'")
                        self.uploadable_collections[rel_path] = UploadableCollection(self.s3, self, file_path, rel_path,
                                                                                     self.metadatawriter,
                                                                                     self.fileactions,
                                                                                     self.logger, self.notifier)
                        self.uploadable_collections_status[rel_path] = uc_status_init.copy()
                    else:
                        pass  # silently ignore paths that aren't deep enough.

            if file_path.is_file():
                if rel_path.parent not in self.uploadable_collections:
                    depth = len(rel_path.parent.parts)  # look at directory
                    if depth >= self.config.ue.require_depth:
                        self.logger.info(
                            f"Creating UploadableCollection to receive file create '{rel_path.parent}', '{file_path.parent}'")
                        self.uploadable_collections[rel_path.parent] = UploadableCollection(self.s3, self,
                                                                                            file_path.parent,
                                                                                            rel_path.parent,
                                                                                            self.metadatawriter,
                                                                                            self.fileactions,
                                                                                            self.logger,
                                                                                            self.notifier)
                        self.uploadable_collections_status[rel_path.parent] = uc_status_init.copy()
                self.logger.debug(f"Checking if UploadableCollections need new file {file_path}")
                for key, collection in self.uploadable_collections.items():
                    if self.path_ends_with(file_path.parent, key):
                        if collection.check_new_file(file_path):
                            self.logger.debug(f"Hit UploadableCollection {key}")
                            # if collection.ready_to_upload():
                            # self.logger.info(f"Ready to upload UploadableCollection {key}")
                            self.uploadable_collections_status[key]["phase"]="uploading"
                            collection.upload_if_ready()
                return
            else:
                return
        except Exception as e:
            self.logger.error("Exception in manage_create {e} ", exc_info=True)

    async def manage_delete(self, rel_path: Path, file_path: Path) -> None:
        self.logger.debug(f"manage_delete {rel_path} {file_path}")
        if rel_path in self.uploadable_collections:
            self.logger.warn(f"Removing UploadableCollection '{rel_path}'")
            del self.uploadable_collections[rel_path]

    async def watch_directory(self) -> None:
        """Watch the directory for new files and upload them."""
        watch_path = Path(self.base_dir / self.config.ue.media_watch_dir)
        self.watch_path = watch_path
        self.logger.info(f"Watching {self.watch_path}, with output dir {self.output_dir}")
        debounce_list = {}
        collection_matcher = re.compile(self.config.ue.collection_matcher)  # filter new directories based on regexp

        # only create one of these
        if GenAIModuleRemote.monitor_task is None:
            GenAIModuleRemote.monitor_task = asyncio.create_task(asyncio.to_thread(GenAIModuleRemote.listener.monitor))

        self.loop = asyncio.get_running_loop()
        async for changes in awatch(watch_path):
            for change, file_path in changes:
                file_path = Path(file_path)
                rel_path = file_path.relative_to(watch_path.resolve())
                if log_file_watch_detail: self.logger.debug(f"Change: {change.name} {rel_path}")
                if change == Change.added or (self.config.ue.upload_on_modified and change == Change.modified):
                    if rel_path in debounce_list:
                        t = time.time() - debounce_list[rel_path]
                        if t < self.DEBOUNCE_SEC:
                            if log_file_watch_detail: self.logger.debug(
                                f"Debounce {t:0.3f} {rel_path}")  # required for things like echo foo > foo.txt
                        else:
                            del debounce_list[rel_path]
                            # self.logger.warning(f"Upload already in progress, re-upload not implemented.")
                    else:
                        debounce_list[rel_path] = time.time()
                        # Schedule the upload without awaiting (i.e. fire-and-forget)
                        if file_path.is_dir() and not re.fullmatch(collection_matcher, str(rel_path.name)):
                            if log_file_watch_detail: self.logger.warning(
                                f"Skipping new path '{rel_path.name}' (isdir: {file_path.is_dir()}) that does not match module's collection format '{self.config.ue.collection_matcher}'")
                            continue
                        if log_file_watch_detail: self.logger.debug(f"Detected file or directory: {rel_path}")
                        asyncio.create_task(self.manage_create(rel_path, file_path))
                elif change == Change.deleted:
                    asyncio.create_task(self.manage_delete(rel_path, file_path))
