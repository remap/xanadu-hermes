
import requests

import requests    # pip install requests
from pythonosc import dispatcher    # pip install python-osc
from pythonosc.osc_message import OscMessage
from pythonosc import osc_server
import json
import argparse
import os
import sys
from datetime import datetime



def jprint(text):
    if isinstance(text,list):
        for t in text:
            print(json.dumps(t, indent=4))
    else:
        print(json.dumps(text, indent=4))
def tsformat(ts):
    return ts.strftime("%Y-%m-%d %H:%M:%S.%f")
def setParam(json,field,value):
    json["body"]["parameters"][field] = value
def splitHostPort(s):
    host,port = s.split(":")
    return (host,int(port))

if __name__=="__main__":

    # Use argparse to handle command line arguments
    parser = argparse.ArgumentParser(description='Send a command to Unreal Engine via Remote Control API')
    parser.add_argument('-ueclient', type=str, help='unreal client host:port', default="127.0.0.1:30010")
    parser.add_argument('-oscserver', type=str, help='OSC server host:port', default="0.0.0.0:8000")
    parser.add_argument('-skipuecheck', action='store_true', help='Skip checking for ue connectivity first')
    parser.add_argument('-runosc', type=str)
    args = parser.parse_args()

    ## OSC
    (oscServerHost,oscServerPort) = splitHostPort(args.oscserver)

    ## UE5
    (ueClientHost,ueClientPort) = splitHostPort(args.ueclient)
    ueURL = "http://" + ueClientHost + ":" + str(ueClientPort)

    prefix_editor = "/Game/_Sets/Xanadu_Fall24_v001/"
    prefix_PIE = "/Game/_Sets/Xanadu_Fall24_v001/UEDPIE_0_"
    prefix = prefix_PIE

    ##  JSON
    messageRoot = "messages"
    internalMessageRoot = os.path.join("messages","_internal")


    print("OSC Server:", oscServerHost, oscServerPort)
    print("UE Client:", ueClientHost, ueClientPort)
    print("UE Path Prefix:", prefix)
    print("Message file root:", messageRoot)

if __name__ in {"__main__", "__mp_main__"}:
    from nicegui import app, ui

    dark = ui.dark_mode()
    # ui.label('page with custom title')
    # thread = threading.Thread(target=ui.run, kwargs={"title":"CueProxy", "port":10000})
    # thread.start
    app.native.window_args['resizable'] = False
    app.native.start_args['debug'] = True
    app.native.settings['ALLOW_DOWNLOADS'] = True

    ui.label('app running in native mode')
    ui.button('enlarge', on_click=lambda: app.native.main_window.resize(1000, 700))

    ui.run(native=True, window_size=(400, 300), fullscreen=False)
