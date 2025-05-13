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
root = Path("../ch/jb_testing")
root = Path("/Users/remap/ch-live-gaia/jb_testing")
samples = Path("/Users/remap/ch-live-gaia/test_sketches")

modules =  ["ch2"]
modules =  ["ch1","ch2","ch3"]
muses = ["melpomene",
         "calliope",
         "thalia",
         "euterpe",
         "terpsicore",
         "erato",
         "kira"]


def pick_random_exr(folder_path):
    #print(f"{folder_path}/*.exr")
    exr_files = glob.glob(f"{folder_path}/*.exr")
    if not exr_files: raise FileNotFoundError(f"No .exr files found in {folder_path!r}")
    return random.choice(exr_files)

n = 15   # delay in seconds
n = 60   # delay in seconds
doCopy = True
while True:

    print('\n-------')

    # pick a random module
    module = random.choice(modules)

    # for each muse, copy seven different tests
    random.shuffle(muses)
    now = datetime.datetime.now()
    run = now.strftime("%y%m%d%H%M%S")

    print(module, run)
    for muse in muses:
        source = root / module / "sample_input" / muse
        source = samples
        dest = root / module / "in" / muse / run
        file = pick_random_exr(source)
        os.makedirs(dest, exist_ok=True)
        print(f"copy {file} to {dest}")
        if doCopy: shutil.copyfile(file, dest / "sketch.exr" )

    print(f'pausing {n} seconds')
    time.sleep(n)




