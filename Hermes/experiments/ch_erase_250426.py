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

modules =  ["ch1", "ch2", "ch2-siren", "ch3"]

muses = ["melpomene",
         "calliope",
         "thalia",
         "euterpe",
         "terpsicore",
         "erato",
         "kira"]


def pick_random_exr(folder_path):
    exr_files = glob.glob(f"{folder_path}/*.exr")
    if not exr_files: raise FileNotFoundError(f"No .exr files found in {folder_path!r}")
    return random.choice(exr_files)

eraseInputs = True
eraseOutputs = True


if eraseInputs:
    for module in modules:
        for muse in muses:
            folder =  root / module / "in" / muse
            for child in folder.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                    print ("remove", child )
if eraseOutputs:
    for module in modules:
        for muse in muses:
            folder =  root / module / "out" / muse
            for child in folder.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                    print ("remove", child )

