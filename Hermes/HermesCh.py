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

if __name__ == "__main__":

    # Logger
    path = Path("logconfig-ch.json")
    with path.open("r", encoding="utf-8") as f:
        logconfig = json.load(f)
    logging.config.dictConfig(logconfig)
    logger = logging.getLogger("main")
    logger.setLevel(logging.DEBUG)

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

    # File watching
    pending_uploads = {}
    DEBOUNCE_SEC = 1


    def load_remote_configs(s3, sqs, sns, common_config: str, module_dir: str, module_config_filename: str) -> dict:
        module_dir = Path(module_dir)
        remotes = {}
        for subpath in module_dir.iterdir():
            if subpath.is_dir():
                config_file = subpath / module_config_filename
                if config_file.exists():
                    try:
                        remote = GenAIModuleRemote(s3, sqs, sns, config_file, config_common_file=common_config,
                                                   base_dir=subpath, logger=logger)
                        remotes[remote.config.module] = remote
                        logger.info(f"Loaded config for module '{remote.config.module}' from {config_file}")
                    except Exception as e:
                        logger.error(f"Failed to load module config for module: {e}",
                                     exc_info=True)
                else:
                    logger.warning(f"No config.json found in {subpath}")
        return remotes


    ## Config data is configured per module
    instance = "jb_testing"
    logger.info(f"Hermes Ch Instance: {instance}")
    remotes = load_remote_configs(s3=s3, sqs=sqs, sns=sns, common_config=f"ch/modules/{instance}/config-common.json",
                                  module_dir=f"ch/modules/{instance}", module_config_filename="config.json")

    ## Dynamic data is created at run-time during the show
    ## It is what is watched for.
    ##
    ## Probably we want to use user/group to match up with the directories...
    # TODO: Variable for that
    ##
    for module_name, remote in remotes.items():
        remote.load_dynamic({
            # These are the files to watch for (so far across all modules)
            "media_files": [
                {
                    "name": "media.png",
                    "mimetype": "image/png"
                },
                {
                    "name": "media.exr",
                    "mimetype": "image/x-exr"
                }
            ],
            "metadata_file": "metadata.json",
            "user": "alice",
            "group": "users",
            "tags": ["tag1", "tag2"],
            "timestamp": "2025-01-31T12:00:00"
        })
        # print("---- CONFIG ----")
        # pprint(remote.config)
        # print("---- DYNAMIC ----")
        # pprint(remote.dynamic)
        # metadata_rendered = remote.render_template()
        # print("---- METADATA ----")
        # print (jformat(metadata_rendered))
        # print(remote.write_template())

    #logger.info("Running async watchers...")
    async def watch():
        tasks = [remote.watch_directory() for remote in remotes.values()]
        await asyncio.gather(*tasks)

    asyncio.run(watch())
