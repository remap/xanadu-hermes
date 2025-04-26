import shutil, os, sys
from pathlib import Path
import random
import time
import random
from quickdraw import QuickDrawData
import subprocess
import tempfile

root = Path("../ch/jb_testing")

modules = ["ch1", "ch2", "ch2-siren", "ch3"]

subs = ["in", "out", "sample_input", "prompt", "failover"]

muses = ["melpomene",
         "calliope",
         "thalia",
         "euterpe",
         "terpsicore",
         "erato",
         "kira"]

import ssl

ssl._create_default_https_context = ssl._create_unverified_context
import pandas as pd, json


#### GET MUSE IMAGE LINKS
####
print("\n***** IMAGE LINKS *****")
# Muse images -https://docs.google.com/spreadsheets/d/1EIe9OFpqO1Wc0sYjNSKXhSRBO7k17v9wZE34b3F3TJ4/edit?gid=1507851260#gid=1507851260
df = pd.read_csv(
    'https://docs.google.com/spreadsheets/d/1EIe9OFpqO1Wc0sYjNSKXhSRBO7k17v9wZE34b3F3TJ4/gviz/tq?gid=1507851260&tqx=out:csv')
res = {}
for _, r in df.iterrows(): res.setdefault(r['muse'], {})[r['type']] = {'name': r['name'],
                                                                            'image': {'ch1': r["CH1 Muse"],
                                                                                      'ch2': r["CH2-Muse Muse"],
                                                                                      'ch2-siren': r["CH2-Siren Muse"]
                                                                                      },
                                                                            'failover': {'ch1': r["CH1 Failover"],
                                                                                      'ch2': r["CH2-Muse Failover"],
                                                                                      'ch2-siren': r["CH2-Siren Failover"],
                                                                                         'ch2-siren': r[
                                                                                             "CH2-Siren Failover"],
                                                                                         'ch3': r[
                                                                                             "CH3 Failover"]
                                                                                      }
                                                                            }
musedata=res
print(json.dumps(musedata, indent=4))


#### GET STYLE LINKS
####

# Style images - https://docs.google.com/spreadsheets/d/1EIe9OFpqO1Wc0sYjNSKXhSRBO7k17v9wZE34b3F3TJ4/edit?gid=1150153487#gid=1150153487
print("\n***** STYLE LINKS *****")
df = pd.read_csv(
    'https://docs.google.com/spreadsheets/d/1EIe9OFpqO1Wc0sYjNSKXhSRBO7k17v9wZE34b3F3TJ4/gviz/tq?&gid=1150153487&tqx=out:csv')
res = {}
for _, r in df.iterrows():
    res.setdefault(r['muse'], {})["ch1"] = {
        "style" : r["CH1 Style"]
    }
    res.setdefault(r['muse'], {})["ch2"] = {
        "garment": r["CH2 Garment"]
    }
    res.setdefault(r['muse'], {})["ch2-siren"] = {
        "garment": r["CH2-Siren Garment"]
    }
    res.setdefault(r['muse'], {})["ch3"] = {
        "style": r["CH3 Style"]
    }
styledata=res
print(json.dumps(styledata, indent=4))

#### GET SAMPLE SKETCHES
####
print("\n***** SAMPLE SKETCHES *****")
sampledata = {}
# for module in modules:
#     sampledata[module] = []
# df = pd.read_csv(
#     'https://docs.google.com/spreadsheets/d/1EIe9OFpqO1Wc0sYjNSKXhSRBO7k17v9wZE34b3F3TJ4/gviz/tq?gid=495886552&tqx=out:csv')
# for _, r in df.iterrows():
#     for module in modules:
#         if r[module].lower() == 'x':
#             sampledata[module].append(r["Sketch link"])
# print(json.dumps(sampledata, indent=4))

## Supply a google drive folder
FOLDER_ID = "1T-kciErMS-jG6bD4nvAuemRArnw9a8LC"

import os
from googleapiclient.discovery import build

with open("../xanadu-secret-gdrive.json") as f:
    gdrive_config = json.load(f)
API_KEY   = gdrive_config["api_key"]
service = build("drive", "v3", developerKey=API_KEY)
page_token = None
for module in modules:
    sampledata[module] = []
while True:
    resp = service.files().list(
        q=f"'{FOLDER_ID}' in parents and trashed=false",
        spaces="drive",
        fields="nextPageToken, files(id, name, mimeType)",
        pageSize=1000,
        includeItemsFromAllDrives=True,   # look outside your own My Drive
        supportsAllDrives=True,           # ditto
        pageToken=page_token
    ).execute()

    for f in resp.get("files", []):
        url = f"https://drive.google.com/uc?export=view&id={f['id']}"
        print(f"{f['id']}\t{f['name']}\t{url}")

        for module in modules:
            sampledata[module].append({ "filename" : f['name'], "url" : url})

    page_token = resp.get("nextPageToken")
    if not page_token:
        break

print("\n***** BUILD DIRECTORIES *****")
#### BUILD DIRECTORIES
####

for module in modules:
    for sub in subs:
        for muse in muses:
            d = root / module / sub / muse
            print(d)
            os.makedirs(d, exist_ok=True)



###  COPY FILES
###
from urllib.request import urlretrieve
import traceback

print("\n***** RETRIEVE AND STORE FILES *****")

preview = True
copySamples = True
errors = 0

def retrieve(url, dest):
    print(f"retrieve {url} {dest}")
    if not preview: urlretrieve(url, dest)


if copySamples:
    print("Samples")
    for module in sampledata:
        for sample in sampledata[module]:
            try:
                print(sample)
                url = sample["url"]
                filename = sample["filename"]
                fd, temp_file_name = tempfile.mkstemp()
                retrieve(url, temp_file_name )
                for muse in muses:
                    dest = root / module / 'sample_input' / muse / filename
                    print (f"copy {temp_file_name} {dest}")
                    if not preview: shutil.copy(temp_file_name, dest )
                os.close(fd)
                os.remove(temp_file_name)
            except Exception as e:
                errors += 1
                traceback.print_exc()

for module in ["ch1", "ch2", "ch2-siren"]:
    print(f"{module} Muse")
    for muse in muses:
        try:
            url = musedata[muse]["principal"]["image"][module]
            dest = root / module / "prompt" / muse / "muse.png"
            retrieve(url,dest)
            if "understudy" in musedata[muse]:
                url = musedata[muse]["understudy"]["image"][module]
                dest = root / module / "prompt" / muse / "muse-understudy.png"
                retrieve(url, dest)
        except Exception as e:
            errors += 1
            traceback.print_exc()

for module in ["ch1", "ch3"]:
    print(f"{module} Style")
    for muse in muses:
        try:
            url = styledata[muse][module]["style"]
            dest = root / module / "prompt" / muse / "style.png"
            retrieve(url,dest)
        except Exception as e:
            errors += 1
            traceback.print_exc()

for module in ["ch2", "ch2-siren"]:
    print(f"{module} Garment")
    for muse in muses:
        try:
            url = styledata[muse][module]["garment"]
            dest = root / module / "prompt" / muse / "garment_sketch.png"
            retrieve(url,dest)
        except Exception as e:
            errors += 1
            traceback.print_exc()

print("Failover")
for module in modules:
    for muse in muses:
        try:
            url = musedata[muse]["principal"]["failover"][module]
            dest = root / module / "failover" / muse / "output.png"
            retrieve(url,dest)
            if "understudy" in musedata[muse]:
                url = musedata[muse]["understudy"]["failover"][module]
                dest = root / module / "failover" / muse / "output-understudy.png"
                retrieve(url, dest)
        except Exception as e:
            errors += 1
            traceback.print_exc()

print("\n------\n")
print(f"Retrieval errors: {errors}")
