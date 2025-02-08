import json
import jinja2
from types import SimpleNamespace
import tempfile
import os
import logging
from pathlib import Path
from jsonmerge import merge
from pprint import pprint
import time
import re
import asyncio
from watchfiles import awatch, Change
from hermes.utils import jformat
from pprint import pprint
def to_namespace(d):
    return SimpleNamespace(**{k: to_namespace(v) if isinstance(v, dict) else v for k, v in d.items()})
import boto3
from datetime import datetime
TIME_STRING_FORMAT = "%Y-%m-%dT%H:%M:%S"

import mimetypes
mimetypes.add_type("image/x-exr", ".exr")

import subprocess

## config_common_file :  Common configuration file (optional), which can be overridden
## config file:  module-specific config
## output-dir:  while to put stuff

from hermes.ch.collection import UploadableCollection
from hermes.ch.aws import SQSNotifier

class GenAIModuleRemote:

    # self.config and self.dynamic are module-wide vars
    # to override for writing a specific metadata, pass overrides into metadata  template

    def __init__(self, s3, sqs, config_file: str, config_common_file: str = None, base_dir = '.', logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.s3 = s3
        self.sqs = sqs
        self.base_dir = Path(base_dir)
        self.config_file = Path(config_file)
        self.config_dir = self.config_file.parent
        self.config_common_file = Path(config_common_file)
        self.DEBOUNCE_SEC = 1
        self.uploadable_collections = {}
        self.dynamic_vars = {}  # dict version
        self.dynamic = None # Becomes simplenamespace of dynamic_vars
        if  self.config_common_file is not None:
            try:
                with open(self.config_common_file) as f:
                    config_str = f.read()
                self._config_dict = json.loads(config_str)
            except json.JSONDecodeError as e:
                self.logger.error("Invalid JSON in config file '%s': %s", self.config_file, e)
                raise
        else:
            self._config_dict = {}
        try:
            with open(self.config_file) as f:
                config_str = f.read()
            self._config_dict = merge(self._config_dict, json.loads(config_str))
        except json.JSONDecodeError as e:
            self.logger.error("Invalid JSON in config file '%s': %s", self.config_file, e)
            raise
        self.config = to_namespace(self._config_dict)
        self.output_dir = self.base_dir / Path(self.config.metadata.output_dir)
        self.notifier = SQSNotifier(self.sqs, self.config.sqs.notify_url, self.config.s3.input_bucket, self.config.pipeline.name, self.config.module, self.config.pipeline.start_phase, self.logger)

    def load_dynamic(self, dynamic_vars: dict, merge=False):
        if merge:
            self.dynamic_vars = self.dynamic_vars | dynamic_vars
        else:
            self.dynamic_vars = dynamic_vars
        self.dynamic = to_namespace(self.dynamic_vars)
        self._extra_vars = self.dynamic_vars

    def render_template(self, template_path = None, overrides ={}):
        if template_path is None: template_path = self.config_dir / self.config.metadata.template_file
        try:
            with open(template_path) as f:
                tmpl = f.read()
            template = jinja2.Template(tmpl)
            context = {"config": self.config, **(self._extra_vars | overrides), "dynamic": self.dynamic}
            rendered = template.render(context)
            return json.loads(rendered)
        except json.JSONDecodeError as e:
            self.logger.error("Error decoding JSON from rendered template '%s': %s", template_path, e)
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
        overrides= {
                "metadata_file" : metadata_file["s3_unique_name"],
                "media_files" : [ { 'name' : f['s3_unique_name'], 'mimetype' : f['mimetype'] } for f in media_files.values() ],
                "timestamp": datetime.now().strftime(TIME_STRING_FORMAT)
            }
        return json.dumps(self.render_template(overrides=overrides), indent=4)

    async def convert_exr_to_png(self, filepath_in, filepath_out):
        await asyncio.sleep(0)
        command = [
            "magick",
            filepath_in,
            "-alpha", "off",
            "-colorspace", "sRGB",
            "-gamma", "2.2",
            "-sigmoidal-contrast", "5x50%",
            filepath_out
        ]
        self.logger.info(f"convert_exr_to_png, {filepath_in}, {filepath_out}")
        try:
            # Run the command and capture output
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,  # Capture standard output
                stderr=subprocess.PIPE,  # Capture standard error
                text=True,  # Decode output to string
                check=True  # Raise exception if command fails
            )
            # Print the captured output
            if len(result.stdout.strip())> 0: self.logger.debug(f"Command Output: {result.stdout}" )
            if len(result.stderr.strip())> 0: self.logger.error(f"convert_exr_to_png errors: f{result.stderr}")
        except subprocess.CalledProcessError as e:
            # Handle errors
            self.logger.error(f"Error occurred: {e.stderr}")

    def fileactions(self, filepath):
        file = Path(filepath)
        mime_type, encoding = mimetypes.guess_type(filepath)
        self.logger.debug(f"fileactions: {mime_type}, {encoding}, {file}")
        if mime_type=="image/x-exr":
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.convert_exr_to_png(file, file.with_suffix(".png")))
            except Exception as e:
                self.logger.error(f"Error creating async task in fileactions {e}", exc_info=True)

    async def manage_create(self, rel_path: Path, file_path: Path) -> None:
        try:
            if file_path.is_dir():
                if rel_path in self.uploadable_collections:
                    self.logger.warn(f"Skipping creation of UploadableCollection '{rel_path}', already seen")
                else:
                    self.logger.info(f"Creating UploadableCollection '{rel_path}'")
                    self.uploadable_collections[rel_path] = UploadableCollection(self.s3, self, file_path, rel_path, self.metadatawriter, self.fileactions, self.logger)
            if file_path.is_file():
                if rel_path.parent not in self.uploadable_collections:
                    self.logger.info(f"Creating UploadableCollection to receive file create '{rel_path.parent}', '{file_path.parent}'")
                    self.uploadable_collections[rel_path.parent] = UploadableCollection(self.s3, self, file_path.parent, rel_path.parent, self.metadatawriter, self.fileactions, self.logger)
                self.logger.debug(f"Checking if UploadableCollections need new file {file_path}")
                for key, collection in self.uploadable_collections.items():
                    if collection.check_new_file(file_path):
                        self.logger.debug(f"Hit UploadableCollection {key}")
                        #if collection.ready_to_upload():
                            #self.logger.info(f"Ready to upload UploadableCollection {key}")
                        collection.upload_if_ready(self.notifier)
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


        # self.state = State.UPLOADING
        # # for all media
        # self.upload_to_s3(file_path)
        #
        # self.state = State.UPLOADING

    async def watch_directory(self) -> None:
        """Watch the directory for new files and upload them."""
        watch_path = Path(self.base_dir / self.config.ue.media_watch_dir)
        self.logger.debug(f"Module {self.config.module} watching {watch_path}")
        debounce_list = {}
        collection_matcher = re.compile(self.config.ue.collection_matcher)   # filter new directories based on regexp
        async for changes in awatch(watch_path):
            for change, file_path in changes:
                file_path = Path(file_path)
                rel_path = file_path.relative_to(watch_path.resolve())
                self.logger.debug(f"Change: {change.name} {rel_path}")
                if change == Change.added or (self.config.ue.upload_on_modified and change == Change.modified):
                    if rel_path in debounce_list:
                        t = time.time() - debounce_list[rel_path]
                        if t < self.DEBOUNCE_SEC:
                            self.logger.debug(f"Debounce {t:0.3f} {rel_path}")  # required for things like echo foo > foo.txt
                        else:
                            del debounce_list[rel_path]
                            #self.logger.warning(f"Upload already in progress, re-upload not implemented.")
                    else:
                        debounce_list[file_path] = time.time()
                        # Schedule the upload without awaiting (i.e. fire-and-forget)
                        if file_path.is_dir() and not re.fullmatch(collection_matcher, str(rel_path.name)):
                            self.logger.warning(f"Skipping new path '{rel_path.name}' that does not match module's collection format '{self.config.ue.collection_matcher}'")
                            continue
                        self.logger.debug(f"Detected file or directory: {rel_path}")
                        asyncio.create_task(self.manage_create(rel_path, file_path))
                elif change == Change.deleted:
                    asyncio.create_task(self.manage_delete(rel_path, file_path))

if __name__ == "__main__":
    config_common = {
        "description": "a module",
        "extra" : "extra"
    }
    config_data = {
        "module": "",
        "description": "more specific description",
        "instance": "instance_value",
        "target_environment": "prod",
        "pipeline": "",
        "candidates_to_generate": "",
        "metadata_template_file": "",
        "metadata": {
            "template_file": "metadata_template.json",
            "parser": "jinja2",
            "output_dir": "output"
        },
        "ue": {"media_watch_dir": ""},
        "firebase": {"notify_key": ""},
        "s3": {
            "input_bucket": "input-bucket-value",
            "output_bucket": "output-bucket-value"
        },
        "sqs": {"notify_url": ""},
        "start_phase": ""
    }
    template_data = {
        "media_file": "{{media_file}}",
        "metadata_file": "{{metadata_file}}",
        "input_bucket": "{{config.s3.input_bucket}}",
        "output_bucket": "{{config.s3.output_bucket}}",
        "instance": "{{config.instance}}",
        "target_environment": "{{config.target_environment}}",
        "user": "{{user}}",
        "group": "{{group}}",
        "tags": "{{tags}}",
        "mimetype": "{{mimetype}}",
        "timestamp": "{{timestamp}}"
    }
    with tempfile.NamedTemporaryFile("w+", delete=False) as common_file:
        json.dump(config_common, common_file)
        common_file.flush()
        common_path = common_file.name
    with tempfile.NamedTemporaryFile("w+", delete=False) as config_file:
        json.dump(config_data, config_file)
        config_file.flush()
        config_path = config_file.name
    with tempfile.NamedTemporaryFile("w+", delete=False) as tmpl_file:
        json.dump(template_data, tmpl_file)
        tmpl_file.flush()
        template_path = tmpl_file.name
    processor = GenAIModuleRemote(config_path, config_common_file = common_path)
    processor.logger.setLevel(logging.INFO)
    extra_vars = {
        "media_file": "media.mp4",
        "metadata_file": "meta.json",
        "user": "alice",
        "group": "users",
        "tags": ["tag1", "tag2"],
        "mimetype": "video/mp4",
        "timestamp": "2025-01-31T12:00:00"
    }
    processor.load_dynamic(extra_vars)
    output = processor.render_template(template_path)
    pprint(processor.config)
    print(json.dumps(output, indent=2))
    os.remove(config_path)
    os.remove(common_path)
    os.remove(template_path)
