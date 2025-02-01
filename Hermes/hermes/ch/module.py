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


## config_common_file :  Common configuration file (optional), which can be overridden
## config file:  module-specific config
## output-dir:  while to put stuff
from enum import StrEnum


class State(StrEnum):
    INITIALIZED = "INTALIZED: Initialized"
    WATCHING = "WATCHING: Watching for input files"
    FILES_PARTIAL = "FILES_PARTIAL: Some files detected"
    FILES_ALL = "FILES_ALL: All files detected"
    UPLOAD_IN_PROGRESS = "UPLOAD_IN_PROGRESS: Upload in progress"
    COMPLETE = "COMPLETE: Files uploaded"
    UPLOAD_ERROR = "UPLOAD_ERROR: Error uploading"

import random, string
class UploadableCollection:

    def __init__(self, module: "GenAIModuleRemote", file_path : Path,  rel_path : Path,  logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        self.module = module
        self.path = file_path
        self.rel_path = rel_path
        self.state = State.INITIALIZED
        self.s3_unique_prefix = str(self.rel_path).replace(os.sep, "-") + "-" + self.generate_random_string()
        self.name = f"{file_path} => {self.s3_unique_prefix}"
        self.files = {}
        self.import_module()
        pprint(self.files)

    def import_module(self):
        self.files[ self.module.dynamic.metadata_file ] = dict(path=self.path / Path(self.module.dynamic.metadata_file),
                                                               s3_unique_name=f'{self.s3_unique_prefix}-{self.module.dynamic.metadata_file}',
                                                               mimetype="application/json", have=False, uploaded=False)

        for file in self.module.dynamic.media_files:
            self.files[ file["name"] ] = dict(path=self.path / Path(file["name"]),
                                              s3_unique_name=f'{self.s3_unique_prefix}-{file["name"]}',
                                              mimetype=file["mimetype"],
                                              have=False, uploaded=False)
        self.s3_bucket = self.module.config.s3.input_bucket

    def generate_random_string(self):
        return "".join(random.choices(string.ascii_lowercase + string.ascii_uppercase + string.digits, k=12))

    def ready_to_upload(self):
        return all(x["have"] for x in self.files.values())

    def check_new_file(self, file_path):
        hit = False
        for file in self.files.values():
            if file_path==file["path"]:
                file["have"] = True
                return True
        return False

    def upload_if_ready(self):
        if not self.ready_to_upload():
            return
        self.logger.info(f"Ready to upload {self.name}")
        for file_info in self.files.values():
            asyncio.create_task(self.upload_to_s3(file_info["s3_unique_name"]))
            file_info["uploaded"] = True

    async def upload_to_s3(self, file_path: Path) -> None:
        file_path = Path(file_path)
        filename = file_path.name  # os.path.basename(file_path)
        self.logger.info(f"Uploading {filename} to bucket {self.s3_bucket}...")
        return
        try:
            await asyncio.to_thread(s3.upload_file, file_path, self.s3_bucket, filename)
            self.logger.info(f"Uploaded {filename} successfully.")
            #del pending_uploads[file_path]
            return True
        except Exception as err:
            self.logger.error(f"Error uploading {filename}: {err}")
            return False

class GenAIModuleRemote:



    def __init__(self, config_file: str, config_common_file: str = None, base_dir = '.', logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.base_dir = Path(base_dir)
        self.config_file = Path(config_file)
        self.config_dir = self.config_file.parent
        self.config_common_file = Path(config_common_file)
        self.DEBOUNCE_SEC = 1
        self.uploadable_collections = {}
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

    def load_dynamic(self, dynamic_vars: dict):
        self.dynamic = to_namespace(dynamic_vars)
        self._extra_vars = dynamic_vars

    def render_template(self, template_path = None):
        if template_path is None: template_path = self.config_dir / self.config.metadata.template_file
        try:
            with open(template_path) as f:
                tmpl = f.read()
            template = jinja2.Template(tmpl)
            context = {"config": self.config, **self._extra_vars, "dynamic": self.dynamic}
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
            self.logger.error(f"Error writing rendered template to '{output_path}': {e}")
            raise


    async def new_file_seen(self, rel_path: Path, file_path: Path) -> None:
        if file_path.is_dir():
            self.logger.info(f"Creating UploadableCollection '{rel_path}'")
            self.uploadable_collections[rel_path] = UploadableCollection(self, file_path, rel_path, self.logger)
        elif file_path.is_file():
            self.logger.debug(f"Checking if UploadableCollections need new file {file_path}")
            for key, collection in self.uploadable_collections.items():
                if collection.check_new_file(file_path):
                    self.logger.debug(f"Hit UploadableCollection {key}")
                    #if collection.ready_to_upload():
                        #self.logger.info(f"Ready to upload UploadableCollection {key}")
                    collection.upload_if_ready()
            return
        else:
            return

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
                if change == Change.added:
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
                        self.logger.info(f"Detected new file or directory: {rel_path}")
                        asyncio.create_task(self.new_file_seen(rel_path, file_path))

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
