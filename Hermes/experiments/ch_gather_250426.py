
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




roots = [
    Path("/Users/remap/ch-live-gaia/ch_in_out_before_250516"),
    Path("/Users/remap/ch-live-gaia/ch_in_out_before_250517a"),
    Path("/Users/remap/ch-live-gaia/ch_in_out_before_250517b"),
    Path("/Users/remap/ch-live-gaia/ch_in_out_before_250520")
    ]
out = Path("/Users/remap/ch-live-gaia/gather_for_orbus_250521")

modules =  ["ch1","ch2","ch3"]

muses = ["melpomene",
         "calliope",
         "thalia",
         "euterpe",
         "terpsicore",
         "erato",
         "kira"]

RANGES = ((14,17), (20,23))

def mtime_in_ranges(path: str):
    ts = os.path.getmtime(path)
    hour = time.localtime(ts).tm_hour
    return any(start <= hour < end for start, end in RANGES)

for root in roots:
    for module in modules:
        os.makedirs(out / module, exist_ok=True)
        for muse in muses:
            folder =  root / module / "out" / muse
            print(folder)
            for child in folder.iterdir():
                # for file in (child).glob('*-sketch.exr'):
                #     if file.is_file():
                #         print(f'Found: {file}')
                #         shutil.copy(file, out / module)
                for file in (child).glob('*-output.png'):
                    if file.is_file():
                        if mtime_in_ranges(file):
                            print(f'Found: {file}')
                            shutil.copy(file, out / module)
                # for file in (child).glob('*-sd35_image.png'):
                #     if file.is_file():
                #         print(f'Found: {file}')
                #         shutil.copy(file, out / module)
                for file in (child).glob('*.glb'):
                    if file.is_file():
                        if mtime_in_ranges(file):
                            print(f'Found: {file}')
                            shutil.copy(file, out / module)

