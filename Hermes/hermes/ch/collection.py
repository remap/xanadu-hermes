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

    def __init__(self, s3, module: "GenAIModuleRemote", file_path : Path,  rel_path : Path,  logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.s3 = s3
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
        self.metadata_file_for_notify = f'{self.s3_unique_prefix}-{self.module.dynamic.metadata_file}'
        self.files[ self.module.dynamic.metadata_file ] = dict(path=self.path / Path(self.module.dynamic.metadata_file),
                                                               s3_unique_name=self.metadata_file_for_notify,
                                                               mimetype="application/json", have=False, uploaded=False, filetype="meta")
        for file in self.module.dynamic.media_files:
            self.media_file_for_notify = f'{self.s3_unique_prefix}-{file["name"]}'
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


    def check_new_file(self, file_path):
        hit = False
        for file in self.files.values():
            if file_path==file["path"]:
                file["have"] = True
                return True
        return False

    def upload_if_ready(self, notifier):
        if not self.ready_to_upload() or self.all_uploaded():
            return
        self.logger.info(f"Ready to upload {self.name}")
        for file_info in self.files.values():
            if not file_info["uploaded"]:
                asyncio.create_task(self.upload_to_s3(file_info["path"], file_info["s3_unique_name"], notifier))
                file_info["uploaded"] = True
            else:
                self.logger.debug(f'Skipping upload already called for {file_info["path"]}')

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
                notifier.notify(self.media_file_for_notify, self.metadata_file_for_notify)

            return True
        except Exception as err:
            self.logger.error(f"Error uploading {filename}: {err}")
            return False
