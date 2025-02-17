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
import pathlib
from datetime import datetime
import random, string
import jsonpickle
class PosixPathHandler(jsonpickle.handlers.BaseHandler):
    def flatten(self, obj, data):
        return str(obj)
jsonpickle.handlers.register(pathlib.PosixPath, PosixPathHandler)

TIME_STRING_FORMAT = "%Y-%m-%dT%H:%M:%S"

class UploadableCollection:

    def __init__(self, s3, module: "GenAIModuleRemote", file_path : Path,  rel_path : Path, metadatawriter=None, file_actions=None, logger=None, notifier=None, loadExisting=False):
        self.logger = logger or logging.getLogger(__name__)
        self.s3 = s3
        self.logger.setLevel(logging.DEBUG)
        self.module = module
        self.path = file_path
        self.rel_path = rel_path
        self.name = f"{file_path} => "
        self.files = {}
        self.metadata_file = None
        self.notifier = notifier
        self.last_upload_time = None
        self.upload_count = 0

        if metadatawriter is None:
            self.metadatawriter = self.simplemetadatawriter
        else:
            self.metadatawriter = metadatawriter

        # Load file data and then set up actions
        self.import_module()
        if file_actions is not None:
            if type(file_actions) is list:
                self.file_actions = file_actions
            else:
                self.file_actions = [file_actions]
        #pprint(self.files)

        # If the directory is created with files in it (e.g., a folder copy)
        # May not trigger changes for everything already there.
        # If that becomes an issues, could use this:
        # TODO: The relationship of this with actions needs work... (png changes underneath)
        self.loadExisting = loadExisting
        if self.loadExisting:
            for item in self.path.resolve().iterdir():
                if item.is_file():
                    logging.warning(f'Collection {self.name} loading existing {item}')
                    self.check_new_file(item)
            self.upload_if_ready()


    def to_summary(self):
        s = {}
        #s["name"] = self.name
        s["rel_path"] = self.rel_path
        s["s3_unique_prefix"] = self.s3_unique_prefix
        s["last_upload_time"] = self.last_upload_time
        s["upload_count"] = self.upload_count
        s["metadata_file"] = self.metadata_file
        s["media_files"] = self.files
        return s

    def to_json(self):
        return jsonpickle.encode(self.to_summary(), unpicklable=False)

    def gen_unique_s3_prefix(self):
        self.s3_unique_prefix = str(self.rel_path).replace(os.sep, "-") + "-" + self.generate_random_string()
        self.name = f"{self.path} => {self.s3_unique_prefix}"

    def import_module(self):
        self.gen_unique_s3_prefix()
        # Metadata handle specially as it will be built after we have all the files
        self.metadata_file_for_notify = f'{self.s3_unique_prefix}-{self.module.dynamic.metadata_file}'
        self.metadata_file = dict(path=self.path / Path(self.module.dynamic.metadata_file),
                                                             s3_unique_name=self.metadata_file_for_notify,
                                                             mimetype="application/json", have=False, uploaded=False,
                                                             uploading=False, filetype="meta")
        self.media_files_for_notify = {}
        for file in self.module.dynamic.media_files:
            self.media_files_for_notify[ file["name"] ] = f'{self.s3_unique_prefix}-{file["name"]}'
            self.files[ file["name"] ] = dict(path=self.path / Path(file["name"]),
                                              s3_unique_name=f'{self.s3_unique_prefix}-{file["name"]}',
                                              mimetype=file["mimetype"],
                                              have=False, uploaded=False, uploading=False, filetype="media")
        self.s3_bucket = self.module.config.s3.input_bucket

    def generate_random_string(self):
        return "".join(random.choices(string.ascii_lowercase + string.ascii_uppercase + string.digits, k=12))

    def ready_to_upload(self):
        return all(x["have"] for x in self.files.values())

    def all_uploading(self):
        return all(x["uploading"] for x in self.files.values())

    def all_uploaded(self):
        return all(x["uploaded"] for x in self.files.values())

    def reset_counters(self):
        self.import_module()

    def check_new_file(self, file_path):
        hit = False
        for file in self.files.values():
            #print("check", file_path, file["path"], file_path==file["path"])
            if file_path==file["path"]:
                file["have"] = True
                if self.file_actions is not None:
                    for f in self.file_actions:
                        f(file["path"])
                return True
        return False

    def upload_if_ready(self):
        # Todo : simplify state management
        if not self.ready_to_upload() or self.all_uploaded() or self.all_uploading():
            return
        self.logger.info(f"Ready to upload {self.name}, calling metadatawriter for {self.metadata_file['path']}")
        #print (self.to_json_str())
        try:  # Write the metadata
            if self.metadatawriter:
                metadata = self.metadatawriter(self.metadata_file, self.files)
                with open(self.metadata_file['path'] , "w") as file:
                    file.write(metadata)
                    file.flush()
        except Exception as e:
            self.logger.debug(f"Exception writing metadata", exc_info=True)

        for file_info in self.files.values():
            if not file_info["uploaded"] and not file_info["uploading"]:
                asyncio.create_task(self.upload_to_s3(file_info, self.notifier))
                file_info["uploading"] = True
            else:
                self.logger.debug(f'Skipping upload already done for {file_info["path"]}')

        if not self.metadata_file["uploaded"] and not self.metadata_file["uploading"]:
            asyncio.create_task(self.upload_to_s3(self.metadata_file, self.notifier))
            self.metadata_file["uploading"] = True
        else:
            self.logger.debug(f'Skipping upload already done for {self.metadata_file["path"]}')

    async def upload_to_s3(self, file_info, notifier = None) -> None:
        file_path = Path(file_info["path"])
        key = file_info["s3_unique_name"]
        filename = file_path.name  # os.path.basename(file_path)
        self.logger.info(f"Uploading {filename} to bucket {self.s3_bucket}...")
        try:
            # Not sure whether it matters whether it is using threads
            await asyncio.to_thread(self.s3.upload_file, file_path, self.s3_bucket, key, Config = boto3.s3.transfer.TransferConfig(use_threads=False))#filename)
            self.logger.info(f"Uploaded {filename} to {key} successfully.")
            file_info["uploaded"] = True
            file_info["uploading"] = False
            #del pending_uploads[file_path]
            ## TODO Here? Plus array
            if self.all_uploaded():
                if notifier is not None:
                    notifier.notify(self.media_files_for_notify, self.metadata_file_for_notify)
                self.last_upload_time = datetime.now().strftime(TIME_STRING_FORMAT)
                self.upload_count += 1
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