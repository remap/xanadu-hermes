

import shutil, os
from pathlib import Path
import random

groups = ["melpomene",
      "calliope",
      "thalia",
      "euterpe",
      "terpsicore",
      "erato",
      "kira"]

modules = ["ch1", "ch2", "ch3", "ch4"]

instances = ["jb_testing"]

root_dir = Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/modules/")
media_file = Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/media.exr")
input_subdir = "input"
output_subdir = "output"
trials = 1
users = 2

# Prep dirs
for instance in instances:

    for module in modules:

        input_dir = root_dir / instance / module / input_subdir
        output_dir = root_dir / instance / module / output_subdir

        print("rmtree", input_dir)
        try:
            shutil.rmtree(input_dir)
        except Exception as e:
            print(e)
        print("rmtree", output_dir)
        try:
            shutil.rmtree(output_dir)
        except Exception as e:
            print(e)

        print("makedirs", input_dir)
        os.makedirs(input_dir, exist_ok=True)
        print("makedirs", output_dir)
        os.makedirs(output_dir, exist_ok=True)

# Make samples
print("---")
random.shuffle(instances)
random.shuffle(modules)
random.shuffle(groups)

print(instances, modules, groups)

for instance in instances:
    for module in modules:
        for group in groups:
            for m in range(users):
                user = str(random.randrange(0,10000))

                for n in range(trials):
                    trial = str(random.randrange(0, 10000))

                    media_dir = root_dir / instance / module / input_subdir / group / user / trial
                    print("makedirs", media_dir)
                    os.makedirs(media_dir, exist_ok=True)

