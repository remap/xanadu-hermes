

import logging
import logging.config
from hermes.utils import ColorFormatter

from pathlib import Path
import json
import time

if __name__=="__main__":

    # Setup logger
    path = Path("logconfig-ch.json")
    with path.open("r", encoding="utf-8") as f:
        logconfig = json.load(f)
    logging.config.dictConfig(logconfig)
    logger = logging.getLogger("main")
    logger.setLevel(logging.DEBUG)



    # !/usr/bin/env python3
    import os
    import asyncio

    import boto3
    from watchfiles import awatch, Change


    # Configuration
    S3_BUCKET = 'your-s3-bucket'
    WATCH_DIR = '../../chtesting'
    WATCH_PATH = Path(WATCH_DIR)


    logger.info(f"Hermes-Chrysopoeia Watcher {WATCH_PATH.resolve()}")

    # Create an S3 client
    s3 = boto3.client('s3')

    pending_uploads = {}
    DEBOUNCE_SEC = 1

    async def upload_to_s3(file_path: str) -> None:
        """Upload a file to the S3 bucket."""
        filename = os.path.basename(file_path)
        logger.info(f"Uploading {filename} to bucket {S3_BUCKET}...")
        try:
            await asyncio.to_thread(s3.upload_file, file_path, S3_BUCKET, filename)
            logger.info(f"Uploaded {filename} successfully.")
        except Exception as err:
            logger.error(f"Error uploading {filename}: {err}")


    async def watch_directory() -> None:
        """Watch the directory for new files and upload them."""
        async for changes in awatch(WATCH_PATH):
            for change, file_path in changes:
                rel_path = Path(file_path).relative_to(WATCH_PATH.resolve())
                logger.debug(f"Change: {change.name} {rel_path}")
                if change == Change.added:
                    if rel_path in pending_uploads:
                        t = time.time() - pending_uploads[rel_path]
                        if t < DEBOUNCE_SEC:
                            logger.debug(f"Debounce {t:0.3f} {rel_path}")
                        else:
                            logger.warning(f"Upload already in progress, re-upload not implemented.")
                    else:
                        logger.info(f"Detected new file: {rel_path}")
                        pending_uploads[rel_path] = time.time()

                    # Schedule the upload without awaiting (i.e. fire-and-forget)
                    #asyncio.create_task(upload_to_s3(file_path))


    if __name__ == '__main__':
        asyncio.run(watch_directory())
