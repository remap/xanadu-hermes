import logging, logging.config
from pathlib import Path
import types, json
import time
import asyncio
from pprint import pprint
import boto3
from watchfiles import awatch, Change
from hermes.utils import ColorFormatter, jformat
from hermes.ch.module import GenAIModuleRemote
from fastapi import FastAPI, Request
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from threading import Thread
from uvicorn import Config, Server
from fastapi.staticfiles import StaticFiles
from pythonosc import osc_message_builder
from starlette.responses import Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
import os
import jsonpickle
from hermes.fb.anonclient import FBAnonClient
from types import SimpleNamespace

port_web = 4243
static_web_dir = "ch/web"

# modules
remotes = {}

# File watching
pending_uploads = {}
DEBOUNCE_SEC = 1

# Configure the instance
# TODO: Change to arguments?
instance = "jb_testing"
environment = SimpleNamespace()
environment.name = "prod"
environment.config_prefix = f"{environment.name}-"
environment.module_config_dir = f"{environment.name}/"


# Logger
path = Path("logconfig-ch.json")
with path.open("r", encoding="utf-8") as f:
    logconfig = json.load(f)
logconfig["handlers"]["file"]["filename"] = f"log/{environment.config_prefix}HermesCh.log"
logging.config.dictConfig(logconfig)
logger = logging.getLogger("main")
logger.setLevel(logging.DEBUG)


uvicorn_logger = logger


class EmbeddedFastAPIServer:
    def __init__(self, host="127.0.0.1", port=port_web, logger=None):
        self.logger = logger
        self.app = FastAPI()
        self.app.add_middleware(
            TrustedHostMiddleware, allowed_hosts=["127.0.0.1"]
        )
        self.host = host
        self.port = port
        self.server_thread = None

        self.config = Config(app=self.app, host=self.host, port=self.port, log_level="warning")
        self.server = Server(config=self.config)
        self._configure_routes()


    def _configure_routes(self):
        # Define request model
        class LineRequest(BaseModel):
            line: int
            content: str

        # Endpoint to load file content
        @self.app.get("/get-status")
        async def get_status():
            status = {}
            for key, remote in remotes.items():
                status[key] = remote.to_summary()
            return {"content": status }
            # if not os.path.exists(self.persistFile):
            #     raise HTTPException(status_code=404, detail="File not found.")
            # with open(self.persistFile, "rb") as f:
            #     content = f.read()
            # return {"content": content}

        if os.path.exists(static_web_dir):
            self.app.mount("/", StaticFiles(directory=static_web_dir, html=True), name="static")
        else:
            raise FileNotFoundError(f"Static file '{static_web_dir}' not found.")

    def _run_server(self):
        self.server.run()

    def start(self):
        if self.server_thread is None:
            self.server_thread = Thread(target=self._run_server, daemon=True)
            self.server_thread.start()
            print(f"FastAPI server started at http://{self.host}:{self.port}")

    def stop(self):
        if self.server.started and self.server.should_exit is False:
            self.server.should_exit = True
            print("FastAPI server stopped.")



if __name__ == "__main__":

    # Create the server instance
    server = EmbeddedFastAPIServer(host="127.0.0.1", port=port_web, logger=logger)

    # Start the server in a separate thread
    server.start()

    # AWS secrets
    with open("xanadu-secret-aws.json") as f:
        config = types.SimpleNamespace(**json.load(f))
    session = boto3.Session(
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        region_name=config.region_name
    )

    # Create an S3 client
    s3 = session.client('s3')
    sqs = session.client('sqs')
    sns = session.client('sns')

    # Create Firebase client
    # Anon client with token renewal
    fbclient = FBAnonClient(credentialFile="xanadu-secret-f5762-firebase-adminsdk-9oc2p-1fb50744fa.json", dbURL='https://xanadu-f5762-default-rtdb.firebaseio.com')
    firebase = fbclient.getFB()

    def load_remote_configs(s3, sqs, sns, common_config: str, module_dir: str, module_config_filename: str) -> dict:
        module_dir = Path(module_dir)
        remotes = {}
        for subpath in module_dir.iterdir():
            if subpath.is_dir():
                config_file = subpath / module_config_filename
                if config_file.exists():
                    try:
                        remote = GenAIModuleRemote(s3, sqs, sns, config_file, config_common_file=common_config,
                                                   base_dir=subpath, firebase=firebase, logger=logger)
                        remotes[remote.config.module] = remote
                        logger.info(f"Loaded config for module '{remote.config.module}' from {config_file}")
                    except Exception as e:
                        logger.error(f"Failed to load module config for module: {e}",
                                     exc_info=True)
                else:
                    logger.warning(f"No config.json found in {subpath}")
        return remotes


    ## Config data is configured per module
    logger.info(f"Hermes Ch Instance: {instance}")
    remotes = load_remote_configs(s3=s3, sqs=sqs, sns=sns, common_config=f"ch/modules/{instance}/{environment.config_prefix}config-common.json",
                                  module_dir=f"ch/modules/{instance}", module_config_filename=f"{environment.module_config_dir}config.json")


    for module_name, remote in remotes.items():
        remote.load_dynamic({})

    async def watch():
        tasks = [remote.watch_directory() for remote in remotes.values()]
        await asyncio.gather(*tasks)

    asyncio.run(watch())
