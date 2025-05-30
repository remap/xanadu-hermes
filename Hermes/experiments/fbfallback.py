import time
from hermes.fb.anonclient import FBAnonClient
fbclient = FBAnonClient(credentialFile="xanadu-secret-f5762-firebase-adminsdk-9oc2p-1fb50744fa.json",
                        dbURL='https://xanadu-f5762-default-rtdb.firebaseio.com')
firebase = fbclient.getFB()



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

modules =  ["ch1","ch2","ch3"]

muses = ["melpomene",
         "calliope",
         "thalia",
         "euterpe",
         "terpsicore",
         "erato",
         "kira"]





for module in modules:
    for muse in muses:
        folder =  root / module / "out" / muse
        print(folder)
        for child in folder.iterdir():
            for file in (child).glob('*-output.png'):
                if file.is_file():
                    d = {
                        "addr": "/xanadu/ch/cue/" +  str(Path(file).parent.relative_to(root)).replace("out/",""),
                        "msg":   {'cue': 'SHOW_MEDIA', 'group': muse, 'module': module, 'cue_media': 'http://128.97.240.184:4243/' + str(Path(file).relative_to(root))}
                    }
                    print(d["addr"], d["msg"])
                    result = firebase.post(d["addr"], d["msg"])
                    time.sleep(0.5)
            for file in (child).glob('*.glb'):
                if file.is_file():
                    d = {
                        "addr": "/xanadu/ch/cue/" +  str(Path(file).parent.relative_to(root)).replace("out/",""),
                        "msg": {'cue': 'SHOW_MEDIA', 'group': muse, 'module': module,
                                'cue_media': 'http://128.97.240.184:4243/' + str(Path(file).relative_to(root))}
                    }
                    print(d["addr"], d["msg"])
                    result = firebase.post(d["addr"], d["msg"])
                    time.sleep(0.5)
            #time.sleep(1)
# data = [
# {
#     "addr": "/xanadu/ch/cue/ch1/calliope/250521164501",
#     "msg":  {'cue': 'SHOW_MEDIA', 'cue_media': 'http://128.97.240.184:4243/ch1/out/calliope/250521164501/calliope-250521164501-lllmB0WW71Sm-sketch-output.png'}
# }
#
# ]



