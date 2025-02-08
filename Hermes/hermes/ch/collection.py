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

    def __init__(self, s3, module: "GenAIModuleRemote", file_path : Path,  rel_path : Path, metadatawriter=None, file_actions=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.s3 = s3
        self.logger.setLevel(logging.DEBUG)
        self.module = module
        self.path = file_path
        self.rel_path = rel_path
        if metadatawriter is None:
            self.metadatawriter = self.simplemetadatawriter
        else:
            self.metadatawriter = metadatawriter
        #self.metadatawriter = self.simplemetadatawriter
        self.state = State.INITIALIZED
        self.name = f"{file_path} => "
        self.files = {}
        self.metadata_file = None
        self.import_module()
        if file_actions is not None:
            if type(file_actions) is list:
                self.file_actions = file_actions
            else:
                self.file_actions = [file_actions]
        #pprint(self.files)

    def gen_unique_s3_prefix(self):
        self.s3_unique_prefix = str(self.rel_path).replace(os.sep, "-") + "-" + self.generate_random_string()
        self.name = f"{self.path} => {self.s3_unique_prefix}"

    def import_module(self):
        self.gen_unique_s3_prefix()
        self.metadata_file_for_notify = f'{self.s3_unique_prefix}-{self.module.dynamic.metadata_file}'
        # self.files[ self.module.dynamic.metadata_file ] = dict(path=self.path / Path(self.module.dynamic.metadata_file),
        #                                                        s3_unique_name=self.metadata_file_for_notify,
        #                                                        mimetype="application/json", have=False, uploaded=False, filetype="meta")
        self.metadata_file = dict(path=self.path / Path(self.module.dynamic.metadata_file),
                                                             s3_unique_name=self.metadata_file_for_notify,
                                                             mimetype="application/json", have=False, uploaded=False,
                                                             filetype="meta")
        self.media_files_for_notify = {}
        for file in self.module.dynamic.media_files:
            self.media_files_for_notify[ file["name"] ] = f'{self.s3_unique_prefix}-{file["name"]}'
            self.files[ file["name"] ] = dict(path=self.path / Path(file["name"]),
                                              s3_unique_name=f'{self.s3_unique_prefix}-{file["name"]}',
                                              mimetype=file["mimetype"],
                                              have=False, uploaded=False, filetype="media")
        self.s3_bucket = self.module.config.s3.input_bucket

    def generate_random_string(self):
        return "".join(random.choices(string.ascii_lowercase + string.ascii_uppercase + string.digits, k=12))

    def ready_to_upload(self):
        return all(x["have"] for x in self.files.values())

    def all_uploaded(self):
        return all(x["uploaded"] for x in self.files.values())

    def reset_counters(self):
        self.import_module()

    def check_new_file(self, file_path):
        hit = False
        for file in self.files.values():
            #print(file_path, file["path"], file_path==file["path"])
            if file_path==file["path"]:
                file["have"] = True
                if self.file_actions is not None:
                    for f in self.file_actions:
                        f(file["path"])
                return True
        return False

    def upload_if_ready(self, notifier):
        if not self.ready_to_upload() or self.all_uploaded():
            return
        self.logger.info(f"Ready to upload {self.name}, calling metadatawriter for {self.metadata_file['path']}")
        try:
            if self.metadatawriter:
                metadata = self.metadatawriter(self.metadata_file, self.files)
                with open(self.metadata_file['path'] , "w") as file:
                    file.write(metadata)
                    file.flush()
        except Exception as e:
            self.logger.debug(f"Exception writing metadata", exc_info=True)

        for file_info in self.files.values():
            if not file_info["uploaded"]:
                asyncio.create_task(self.upload_to_s3(file_info["path"], file_info["s3_unique_name"], notifier))
                file_info["uploaded"] = True
            else:
                self.logger.debug(f'Skipping upload already done for {file_info["path"]}')

        if not self.metadata_file["uploaded"]:
            asyncio.create_task(self.upload_to_s3(self.metadata_file["path"], self.metadata_file["s3_unique_name"], notifier))
            self.metadata_file["uploaded"] = True
        else:
            self.logger.debug(f'Skipping upload already done for {self.metadata_file["path"]}')

    async def upload_to_s3(self, file_path: Path, key, notifier) -> None:
        file_path = Path(file_path)
        filename = file_path.name  # os.path.basename(file_path)
        self.logger.info(f"Uploading {filename} to bucket {self.s3_bucket}...")
        # return
        try:
            await asyncio.to_thread(self.s3.upload_file, file_path, self.s3_bucket, key)#filename)
            self.logger.info(f"Uploaded {filename} to {key} successfully.")
            #del pending_uploads[file_path]

            ## TODO Here? Plus array
            if self.all_uploaded():
                notifier.notify(self.media_files_for_notify, self.metadata_file_for_notify)
                self.reset_counters()

            return True
        except Exception as err:
            self.logger.error(f"Error uploading {filename}: {err}", exc_info=True)
            return False

    from pathlib import Path

    def make_json_serializable(self,data):
        if isinstance(data, Path):
            return str(data)  # Convert Path to string
        elif isinstance(data, dict):
            return {key: self.make_json_serializable(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self.make_json_serializable(item) for item in data]
        else:
            return data  # Leave other types unchanged


    def simplemetadatawriter(self, metadata_file, media_files):
        self.logger.info(f"Using default metadatawriter")
        data_serializable = self.make_json_serializable({"metadata": metadata_file} | media_files)
        return json.dumps(data_serializable, indent=4)