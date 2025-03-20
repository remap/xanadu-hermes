

import shutil, os, sys
from pathlib import Path
import random
import time
import random
from quickdraw import QuickDrawData
import subprocess
import tempfile
qd = QuickDrawData()


with open("ch-quickdraw-categories.txt", "r") as file:
    words = file.read().splitlines()

# path = os.getcwd()
# fd, temp_file_name = tempfile.mkstemp()
# temp_file_name+=".png"
# category = random.choice(words)
# i = qd.get_drawing(category)
# category = category.replace(" ", "-")
# pngfile = temp_file_name  # os.path.join(path, f"sketch-{category}.png")
# exrfile = os.path.join(path, f"sketch-{category}.exr")
# i.image.save(pngfile)
#
# command = ["ffmpeg", "-i", pngfile, "-vf", "scale=384:384", exrfile]
# result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
# print(pngfile, exrfile)
# os.close(fd)
# os.remove(temp_file_name)
# sys.exit(0)


instances = ["jb_testing"]
modules = ["ch1", "ch2", "ch3", "ch4"]
groups = ["melpomene",
      "calliope",
      "thalia",
      "euterpe",
      "terpsicore",
      "erato",
      "kira"]
users = 1
trials = 1


# groups = ["melpomene"]
modules = ["ch1",]
users = 5
trials = 5




root_dir = Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/modules/")
#media_file = Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/media.exr")
media_target_name = "media.exr"
media_files = [
    Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/test_image0.exr"),
    Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/test_image1.exr"),
]
input_subdir = "input"
output_subdir = "output"


create = True
check = True

wait_sec = 5 #

place_wait_sec = 2 # between placing files



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


## TODO: Revise loops below to generalize
##
module = "ch1"

if module=="ch2" or module=="ch1":
    ####### CH2
    # Make samples
    print("---")
    random.shuffle(instances)
    random.shuffle(modules)
    random.shuffle(groups)
    print(instances, modules, groups)
    outputs = []

    root_dir = Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/modules/")
    #humans_dir = Path("//Users/jburke/Dropbox/eutamias-dev/xanadu/data/deepfashion/images")
    humans_dir = Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/data/SHHQ-1.0/no_segment")
    media_dir = Path("")
    media_target_name = "muse.png"
    style_target_name = "sketch.png"

    input_subdir = "input"
    output_subdir = "output"

    human_files = [file for file in os.listdir(humans_dir)]
                   #if "_front" in file.lower()]

    for instance in instances:
        for module in modules:
            for group in groups:
                for m in range(users):
                    user = str(random.randrange(0,10000))

                    for n in range(trials):
                        trial = str(random.randrange(0, 10000))

                        if create:
                            media_dir = root_dir / instance / module / input_subdir / group / user / trial
                            print("makedirs", media_dir)
                            os.makedirs(media_dir, exist_ok=True)

                            media_file = random.choice(human_files)
                            print("ffmpeg convert", media_file, media_dir / media_target_name)
                            #shutil.copy(humans_dir / media_file, media_dir / media_target_name)

                            command = ["ffmpeg", "-i", humans_dir / media_file, "-vf", "scale=1024:-1", media_dir / media_target_name]
                            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                            path = os.getcwd()
                            category = random.choice(words)
                            i = qd.get_drawing(category)
                            category = category.replace(" ", "-")
                            pngfile = media_dir / style_target_name  # os.path.join(path, f"sketch-{category}.png")
                            # exrfile = media_dir / media_target_name
                            i.image.save(pngfile)
                            #

                            print(media_file)
                            print(pngfile)
                            print("\n")

                            time.sleep(place_wait_sec)

                        outputs.append( root_dir / instance / module / output_subdir / group / user / trial )



    sys.exit(0)

if module=="ch3":
    ####### CH3
    # Make samples
    print("---")
    random.shuffle(instances)
    random.shuffle(modules)
    random.shuffle(groups)
    print(instances, modules, groups)
    outputs = []

    root_dir = Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/modules/")
    #media_file = Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/media.exr")
    media_target_name = "content.png"

    style_target_name = "style.png"
    style_files = [
        Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/modules/jb_testing/ch3/_sample-input/0/style.png"),
        Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/modules/jb_testing/ch3/_sample-input/1/style.png"),
        Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/modules/jb_testing/ch3/_sample-input/2/style.png"),
    ]
    input_subdir = "input"
    output_subdir = "output"



    for instance in instances:
        for module in modules:
            for group in groups:
                for m in range(users):
                    user = str(random.randrange(0,10000))

                    for n in range(trials):
                        trial = str(random.randrange(0, 10000))

                        if create:
                            media_dir = root_dir / instance / module / input_subdir / group / user / trial
                            print("makedirs", media_dir)
                            os.makedirs(media_dir, exist_ok=True)

                            style_file = random.choice(style_files)
                            print("copy", style_file, media_dir / style_target_name)
                            shutil.copy(style_file, media_dir / style_target_name)

                            path = os.getcwd()
                            category = random.choice(words)
                            i = qd.get_drawing(category)
                            category = category.replace(" ", "-")
                            pngfile = media_dir / media_target_name  # os.path.join(path, f"sketch-{category}.png")
                            # exrfile = media_dir / media_target_name
                            i.image.save(pngfile)
                            #
                            # command = ["ffmpeg", "-i", pngfile, "-vf", "scale=384:384", exrfile]
                            # result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            print(style_file)
                            print(pngfile)
                            print("\n")

                        outputs.append( root_dir / instance / module / output_subdir / group / user / trial )




    sys.exit(0)

if module=="ch1_old":
    print("---")
    random.shuffle(instances)
    random.shuffle(modules)
    random.shuffle(groups)
    print(instances, modules, groups)
    outputs = []
    ##### CH 1
    root_dir = Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/modules/")
    #media_file = Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/media.exr")
    media_target_name = "media.exr"
    media_files = [
        Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/test_image0.exr"),
        Path("/Users/jburke/Dropbox/eutamias-dev/xanadu/hermes/xanadu-hermes/Hermes/ch/test_image1.exr"),
    ]
    input_subdir = "input"
    output_subdir = "output"



    for instance in instances:
        for module in modules:
            for group in groups:
                for m in range(users):
                    user = str(random.randrange(0,10000))

                    for n in range(trials):
                        trial = str(random.randrange(0, 10000))

                        if create:
                            media_dir = root_dir / instance / module / input_subdir / group / user / trial
                            print("makedirs", media_dir)
                            os.makedirs(media_dir, exist_ok=True)
                            # media_file = random.choice(media_files)
                            # print("copy", media_file, media_dir / media_target_name)
                            # shutil.copy(media_file, media_dir / media_target_name)

                            path = os.getcwd()
                            fd, temp_file_name = tempfile.mkstemp()
                            temp_file_name += ".png"
                            category = random.choice(words)
                            i = qd.get_drawing(category)
                            category = category.replace(" ", "-")
                            pngfile = temp_file_name  # os.path.join(path, f"sketch-{category}.png")
                            exrfile = media_dir / media_target_name
                            i.image.save(pngfile)

                            command = ["ffmpeg", "-i", pngfile, "-vf", "scale=384:384", exrfile]
                            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            print(pngfile, exrfile)
                            os.close(fd)
                            os.remove(temp_file_name)


                        outputs.append( root_dir / instance / module / output_subdir / group / user / trial )

if check:
    while(True):
        time.sleep(wait_sec)
        print("---")
        for output in outputs:
            print(output, "-", list(output.glob("*.png")))