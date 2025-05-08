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
root = Path("/Users/remap/ch-live-gaia/jb_testing_rehearsal")
out = Path("/Users/remap/ch-live-gaia/gather_rehearsal_250506")

modules =  ["ch1","ch2","ch2-siren","ch3"]

muses = ["melpomene",
         "calliope",
         "thalia",
         "euterpe",
         "terpsicore",
         "erato",
         "kira"]





for module in modules:
    os.makedirs(out / module, exist_ok=True)
    for muse in muses:
        folder =  root / module / "out" / muse
        print(folder)
        for child in folder.iterdir():
            for file in (child).glob('*-sketch.exr'):
                if file.is_file():
                    print(f'Found: {file}')
                    shutil.copy(file, out / module)
            # for file in (child).glob('*-output.png'):
            #     if file.is_file():
            #         print(f'Found: {file}')
            #         shutil.copy(file, out / module)
            # for file in (child).glob('*-sd35_image.png'):
            #     if file.is_file():
            #         print(f'Found: {file}')
            #         shutil.copy(file, out / module)
            # for file in (child).glob('*.glb'):
            #     if file.is_file():
            #         print(f'Found: {file}')
            #         shutil.copy(file, out / module)
# n = 15
# doCopy = True
# while True:
#
#     print('\n-------')
#
#     # pick a random module
#     module = random.choice(modules)
#
#     # for each muse, copy seven different tests
#     random.shuffle(muses)
#     now = datetime.datetime.now()
#     run = now.strftime("%y%m%d%H%M%S")
#
#     print(module, run)
#     for muse in muses:
#         source = root / module / "sample_input" / muse
#         dest = root / module / "in" / muse / run
#         file = pick_random_exr(source)
#         os.makedirs(dest, exist_ok=True)
#         print(f"copy {file} to {dest}")
#         if doCopy: shutil.copyfile(file, dest / "sketch.exr" )
#
#     print(f'pausing {n} seconds')
#     time.sleep(n)