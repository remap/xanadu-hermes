import shutil, os, sys
from pathlib import Path
import random
import time
import random
from quickdraw import QuickDrawData
import subprocess
import tempfile
import random
import datetime
import glob
import types
import json
import boto3
import string

root = Path("/Volumes/ch-live-gaia/jb_testing") #/Users/remap/ch-live-gaia/jb_testing")
out = Path("/Volumes/ch-live-gaia/jb_testing/summary.jpg") #/Users/remap/ch-live-gaia/jb_testing/summary.jpg")
aws_bucket = "xanadu-public"
aws_file = "summary.jpg"

modules =  ["ch2","ch3"]

muses = ["melpomene",
         "calliope",
         "thalia",
         "euterpe",
         "terpsicore",
         "erato",
         "kira"]

with open("xanadu-secret-aws.json") as f:
    config = types.SimpleNamespace(**json.load(f))
    session = boto3.Session(
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        region_name=config.region_name
    )

# Create an S3 client
s3 = session.client('s3')

from hermes.fb.anonclient import FBAnonClient

fbclient = FBAnonClient(credentialFile="xanadu-secret-f5762-firebase-adminsdk-9oc2p-1fb50744fa.json",
                        dbURL='https://xanadu-f5762-default-rtdb.firebaseio.com')
firebase = fbclient.getFB()

print(firebase)




latest=[]
for module in modules:
    for muse in muses:
        folder =  root / module / "out" / muse
        dirs = [f for f in folder.iterdir()]
        dirs_sorted = sorted(dirs, key=lambda f: f.stat().st_mtime, reverse=True)
        #print (dirs_sorted)
        n=0
        for child in dirs_sorted:
            if n>0:break
            for file in (child).glob('*-output.png'):
                if file.is_file():
                    if random.randint(0,1) > 0:
                        n+=1
                        print(f'Found {module} {muse}: {file}')
                        latest.append(file)
                        #shutil.copy(file, out / module)
                if n>0: break
        n = 0
        for child in dirs_sorted:
            if n>0:break
            for file in (child).glob('*-sd35_image.png'):
                if file.is_file():
                    if random.randint(0,1) > 0:
                        n+=1
                        print(f'Found {module} {muse}: {file}')
                        latest.append(file)
                        #shutil.copy(file, out / module)
                if n>0: break
subprocess.run( [
    "montage",
    *latest,
    "-tile", "7x2",
    "-geometry", "200x200+5+5",
    str(out)

])
rc = s3.upload_file(out, aws_bucket, aws_file, ExtraArgs={
        'ContentType': 'image/jpeg'
    })
print(f"Upload to aws complete rc={rc}")
t=1
print(f"Sleeping {t} sec")
time.sleep(t)

r = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
msg = "https://xanadu-public.s3.us-west-2.amazonaws.com/summary.jpg?_=" + r
addr="/xanadu/oracle/files"

print("Posting to firebase")
result = firebase.put('https://xanadu-f5762-default-rtdb.firebaseio.com', name=addr, data=msg)

fbclient.stop()