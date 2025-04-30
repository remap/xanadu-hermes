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
root = Path("/Volumes/ch-live-agouti/jb_testing")

modules =  ["ch1", "ch2", "ch2-siren", "ch3"]

muses = ["melpomene",
         "calliope",
         "thalia",
         "euterpe",
         "terpsicore",
         "erato",
         "kira"]

localpath = Path("ch/jb_testing")

for module in modules:
    for muse in muses:
        dest = root / module / "in" / muse
        os.makedirs(dest, exist_ok=True)
        print (dest)
        dest = root / module / "out" / muse
        os.makedirs(dest, exist_ok=True)
        print (dest)



