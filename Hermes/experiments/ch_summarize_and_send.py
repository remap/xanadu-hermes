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
root = Path("/Users/remap/ch-live-gaia/jb_testing")
out = Path("/Users/remap/ch-live-gaia/jb_testing/summary.jpg")

modules =  ["ch2","ch3"]

muses = ["melpomene",
         "calliope",
         "thalia",
         "euterpe",
         "terpsicore",
         "erato",
         "kira"]




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
                    n+=1
                    print(f'Found {module} {muse}: {file}')
                    latest.append(file)
                    #shutil.copy(file, out / module)
                if n>0: break
subprocess.run( [
    "montage",
    *latest,
    "-tile", "4x4",
    "-geometry", "200x200+5+5",
    str(out)

])