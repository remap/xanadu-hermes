import random
import time
import threading
import time
import math
from datetime import datetime, timezone
import string
import os
import json
from unique_names_generator import get_random_name
import firebase_admin  # pip install firebase-admin
from firebase_admin import credentials, db
from unique_names_generator.data import ADJECTIVES, NAMES
import curses
import readchar

muses = ["melpomene",
      "calliope",
      "thalia",
      "euterpe",
      "terpsicore",
      "erato",
      "kira"]


# simple class to random walk location and rotation
# and publish to firebase in the format used
# by the kleroterion 8th wall app

def random_hex_color():
    return f"#{random.randrange(0x1000000):06x}"

class RandomWalk3D:
    change_connected = False

    def __init__(self, name, instance, db):
        self.name = name
        self.instance = instance
        # firebase_admin db setup
        self.ref_peer = db.reference(f"/{self.instance}/kl/peers/{self.name}")
        self.ref_camera = db.reference(f"/{self.instance}/kl/{self.name}/camera-publisher/camera")
        #
        self.group = random.choice(muses)
        self.paint_color = random_hex_color()
        self.position = {"x": 0.0, "y": 0.0, "z": 0.0}  # Starting position at origin
        self.rotation = {"x": 0.0, "y": 0.0, "z": 0.0}  # Starting rotation
        self.t = 0
        self.T0 = int(time.time() * 1000)
        self.connected = True

    def walk(self):
        self.t = int(time.time() * 1000) - self.T0
        dx, dy, dz = (random.uniform(-.2, .2) for _ in range(3))
        drx, dry, drz = (random.uniform(-math.pi / 36.0, math.pi / 36.0) for _ in range(3))  # ±5 degrees in radians

        self.position["x"] += dx
        self.position["y"] += dy
        self.position["z"] += dz
        self.position["t"] = self.t

        self.rotation["x"] = (self.rotation["x"] + drx) % (2 * math.pi)
        self.rotation["y"] = (self.rotation["y"] + dry) % (2 * math.pi)
        self.rotation["z"] = (self.rotation["z"] + drz) % (2 * math.pi)
        self.rotation["t"] = self.t

        # print(f"Walker {self.name} t: {self.t} pos: {self.position}, rot: {self.rotation}")
        # self.db.put_async(f"/{self.instance}/kl/{self.name}/camera-publisher", "camera",
        #                   {"position": self.position, "rotation": self.rotation}, callback=fb_callback)
        if RandomWalk3D.change_connected:
            self.connected = random.choice([True, False])
        self.ref_camera.set(
            {"position": self.position,
             "position_recentered": self.position,
             "rotation": self.rotation,
             "connected": True,
             "group" : self.group,
             "paint_color": self.paint_color,
             "paint_touch": True,
            "connected": self.connected,
             }
        )

    def peer_update(self):
        t = time.time()
        ft = self.format_time_as_iso8601(t)
        unixms = int(t * 1000)
        # print(f"Walker {self.name} peer update: lastSeenUTC: {ft} lastSeenUnix: {unixms}")

        # self.db.put_async(f"/{self.instance}/kl/peers", f"{self.name}",
        #                   {"lastSeenUTC": ft, "lastSeenUnix": unixms,
        #                    "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
        #                    "userData": '{}'}, callback=fb_callback)

        self.ref_peer.set(
            {"lastSeenUTC": ft, "lastSeenUnix": unixms,
             "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
             "userData": '{}',
             "tapped" : True,
             "rnbo_ready" : True,
             "reality" : True,
             "document_visible": True}
        )

    def format_time_as_iso8601(self, t):
        dt = datetime.fromtimestamp(t, tz=timezone.utc)
        formatted_time = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        return formatted_time


# A thread to walk the walkers
# assume peer_interval is slower than interval
def walker_thread(walker_id: str, instance: str, interval: float, peer_interval: float, db: any):
    walker = RandomWalk3D(walker_id, instance, db)
    print(f"Walker {walker_id} started.")
    t0 = time.time()
    while True:
        walker.walk()
        time.sleep(interval)
        t1 = time.time()
        if t1 - t0 > peer_interval:
            walker.peer_update()
            t0 = t1


def main():
    with open("../xanadu-secret-firebase-forwarder.json") as f:
        firebase_config = json.load(f)
    cred = credentials.Certificate("../xanadu-secret-f5762-firebase-adminsdk-9oc2p-1fb50744fa.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': firebase_config['databaseURL']
    })

    ###
    num_walkers = 100  # number of random walkers.
    interval = 0.100  # peroid in seconds to update camera publishers
    peer_interval = 1  # period in seconds to update peer namespace /{instance}/kdl/peers
    instance = 'xanadu'  # instance namespace to use
    idfile = 'walker_ids.txt'  # where to persist ids. delete to create new ids
    change_interval = 10

    ##

    ## Maintain a list of random client ids
    ## Write to a file to limit the number of new ids, which becomes unwieldy to observer in thd db.
    def generate_random_strings(length):
        n = []
        for i in range(0,length):
            n.append(get_random_name(separator='-', style='lowercase', combo=[ADJECTIVES,NAMES]))
        return n
        #return [''.join(random.choices(string.ascii_lowercase + string.digits, k=8)) for _ in range(length)]

    names = []
    if os.path.exists(idfile):
        with open(idfile, 'r') as file:
            names = [line.strip() for line in file.readlines()]
        print(f"Read names {names} from {idfile}")
        if len(names) >= num_walkers:
            names = names[:num_walkers]
    if len(names) < num_walkers:
        names.extend(generate_random_strings(num_walkers - len(names)))
        print(f"Writing names {names} to {idfile}")
        with open(idfile, 'w') as file:
            file.write('\n'.join(names) + '\n')

    ## Launch the threads
    ##
    threads = []
    for i in range(num_walkers):
        wthread = threading.Thread(target=walker_thread, args=(names[i], instance, interval, peer_interval, db))
        wthread.daemon = True
        threads.append(wthread)
        time.sleep(0.05)
        wthread.start()
    print(f"{num_walkers} threads created.\n")
    try:
        next_run = time.time() + change_interval
        dt = random.uniform(change_interval * 0.9, change_interval * 1.5)
        print(f"Next connectivity state change next_run {dt:0.3f}")
        while True:
            now = time.time()
            if RandomWalk3D.change_connected: RandomWalk3D.change_connected = False
            if now >= next_run:
                RandomWalk3D.change_connected = True
                dt = random.uniform(change_interval*0.9, change_interval*1.5)
                print(f"Change connectivity state. next_run {dt:0.3f}")
                next_run = time.time() + dt
            time.sleep(1)  # Keep the main thread alive
    except KeyboardInterrupt:
        print("Stopping walkers.")


if __name__ == "__main__":
    main()
