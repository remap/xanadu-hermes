# API -
# https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-api-http-reference-for-unreal-engine

#
# Example command line use to simulate osc command
# python ./Hermes.py -ueclient "192.168.1.180:30010" -runosc "/xanadu/ue5/call sendFromFileWithReplacement test.json bNewVisibility true"

# Note that our messages require generateTransaction:true to propagate in multiuser editor, I think.

import requests    # pip install requests
from pythonosc import dispatcher    # pip install python-osc
from pythonosc.osc_message import OscMessage
from pythonosc import osc_server
import json
import argparse
import os
import sys
from datetime import datetime
import threading
from nicegui import app, ui

import socketserver, socket

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
    parser.add_argument('-gui',action='store_true',help='experimental gui')
    parser.add_argument('-runosc', type=str)
    args = parser.parse_args()

    ## OSC
    (oscServerHost, oscServerPort) = splitHostPort(args.oscserver)

    ## UE5
    (ueClientHost, ueClientPort) = splitHostPort(args.ueclient)
    ueURL = "http://" + ueClientHost + ":" + str(ueClientPort)

    prefix_editor = "/Game/_Sets/Xanadu_Fall24_v001/"
    prefix_PIE = "/Game/_Sets/Xanadu_Fall24_v001/UEDPIE_0_"
    prefix = prefix_PIE

    ##  JSON
    messageRoot = "messages"
    internalMessageRoot = os.path.join("messages", "_internal")

    print("OSC Server:", oscServerHost, oscServerPort)
    print("UE Client:", ueClientHost, ueClientPort)
    print("UE Path Prefix:", prefix)
    print("Message file root:", messageRoot)


    # Firebase event listener
    # Uses firebase-admin library
    #
    # Firebase Configuration
    with open("xanadu-secret-firebase-forwarder.json") as f:
        firebase_config = json.load(f)


    # Load Firebase credentials
    import firebase_admin
    from firebase_admin import credentials, db  # pip install firebase-admin

    cred = credentials.Certificate("xanadu-secret-f5762-firebase-adminsdk-9oc2p-1fb50744fa.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': firebase_config['databaseURL']
    })

    # https://console.firebase.google.com/u/0/project/xanadu-f5762/database/xanadu-f5762-default-rtdb/data
    # Reference the database path to monitor
    listenPath = "/xanadu/test"
    ref = db.reference(listenPath)

    global fbmsg
    fbmsg = 0
    # Listen for data changes
    from glom import glom, Assign
    def firebaseEventListener(event):
        global fbmsg, fblisteners
        path = f"{listenPath}{event.path}"
        e = {"type": event.event_type, "path": path, "data": event.data}
        if fbmsg==0:
            print("Suppressing initial firebase message", e)
        else:
            print("firebase event", e)

            if path in fblisteners:
                print(path,"-")
                for k,v in fblisteners[path].items():
                    print(k,v)
                    # TODO: Validate
                    if v["action"]["type"].lower() == "echo":
                        print("echo=>", v["action"]["data"].format(path=path,value=event.data))
                    if v["action"]["type"].lower() == "unreal":
                        print("unreal=>")
                        if "parsing" in v:
                            if v["parsing"]["type"] == "glom":
                                #print("glom")
                                spec=Assign(v["parsing"]["spec"], event.data)
                                _ = glom(v, spec)
                        sendMessage(v["action"]["data"], template=True)
        fbmsg+= 1

    # Firebase
    # put interface ... uses firebase simplified client library
    #
    global TCP_TIMEOUT
    TCP_TIMEOUT = 0.15
    # tradeoff here is possibility of dropping data during congestion
    # really we should be streaming out commands as they come in.
    #

    def fb_callback(result):
        print("fb async return", result)

    def handleOSC_KL(addr, *args):
        print("\n-KL--", datetime.today().strftime('%y-%m-%d %H:%M:%S'))
        print("  ", addr)
        print("    k:", args[0])
        if len(args) > 1:
            print("    v:", args[1:])

        result = []
        if (addr).endswith("/kvproperty"):
            if (len(args) % 2) == 1:
                print("  setting trailing null value to empty string")
                args = list(args).append("")
            for i in range(0, len(args), 2):
                print("     ", args[i], args[i + 1])
                firebase.put_async(addr, args[i], args[i + 1], params={'print': 'pretty'},
                                   headers={'X_FANCY_HEADER': 'VERY FANCY'}, callback=fb_callback)
        else:  # if (addr).endswith("/method") or (addr).endswith("/childmethod") or (addr).endswith("/event"):
            result = firebase.post_async(addr, args, params={'print': 'pretty'},
                                         headers={'X_FANCY_HEADER': 'VERY FANCY'}, callback=fb_callback)
    def handleOSC_FB(addr, *args):
        print("\n-FB--", datetime.today().strftime('%y-%m-%d %H:%M:%S'))
        print("  ", addr)
        print("    k:", args[0])
        if len(args) > 1:
            print("    v:", args[1:])

        result = []
        if (addr).endswith("/put"):
            if (len(args) % 2) == 0:
                print("  setting trailing null value to empty string")
                args = list(args).append("")
            for i in range(1, len(args), 2):
                print("     ", args[i], args[i + 1])
                firebase.put_async(args[0], args[i], args[i + 1], params={'print': 'pretty'},
                                   headers={'X_FANCY_HEADER': 'VERY FANCY'}, callback=fb_callback)
        elif (addr).endswith("/post"):
            result = firebase.post_async(args[0], args[1:], params={'print': 'pretty'},
                                headers={'X_FANCY_HEADER': 'VERY FANCY'}, callback=fb_callback)
        elif (addr).endswith("/delete"):
            for i in range(1, len(args)):
                result = firebase.delete(args[0], args[i])

    global fblisteners
    fblisteners = {}
    def handleOSC_FB_LISTEN(addr, *args):
        global fblisteners
        print("\n-FB_LISTEN--", datetime.today().strftime('%y-%m-%d %H:%M:%S'))
        print("  ", addr)
        print("    k:", args[0])
        if (addr).endswith("/listen"):
            print("listen", args[0], args[1])
            # TODO: Validate args
            msgfile = os.path.join(messageRoot, args[1])
            if not os.path.splitext(msgfile)[1]:
                msgfile += '.json'
            with open(msgfile) as json_file:
                msg = json.load(json_file)
            if not args[0] in fblisteners:
                fblisteners[args[0]] = {}
            fblisteners[args[0]][msgfile] = msg
            print("fblisteners",fblisteners)
        elif (addr).endswith("/removelisten"):
            print("removelisten", args[0], args[1])
            msgfile = os.path.join(messageRoot, args[1])
            if not os.path.splitext(msgfile)[1]:
                msgfile += '.json'
            fblisteners[args[0]].pop(msgfile, None)
            if len(fblisteners[args[0]])==0:
                fblisteners.pop(args[0], None)
            print("fblisteners",fblisteners)

    # Replace a specific parameter
    # setParam(msg, "bNewVisibility", True if args.value.lower() in ('true') else False)

    def sendMessage(msgs, url=ueURL, template=False):
        result = []
        if not isinstance(msgs, list):
            msgs = [msgs]

        for msg in msgs:
            # TODO: Should send return codes back
            print(tsformat(datetime.now()), ">", url + msg["request"])
            if "body" in msg:
                headers = {'Content-Type': 'application/json'}
                if template:
                    # TODO: More robust templating
                    if "objectPath" in msg["body"]: msg["body"]["objectPath"] = msg["body"]["objectPath"].replace(
                        "{{prefix}}", prefix)
                jprint(msg["body"])
                data = json.dumps(msg["body"])
            else:
                headers = None
                data = None
            if "method" in msg:
                if msg["method"] == "get":
                    r = requests.get(url + msg["request"], data=data, headers=headers)
            else:
                r = requests.put(url + msg["request"], data=data, headers=headers)
            print(tsformat(datetime.now()), "<", r.status_code, r.reason)
            # jprint(json.loads(r.text))
            result.append(json.loads(r.text))
        return (result)


    def sendFromFile(msgfile, template=True):
        print("sendFromFile", msgfile)
        with open(msgfile) as json_file:
            msg = json.load(json_file)
        return sendMessage(msg, template=template)


    # TODO: Parse arbitrary key-value pairs and/or JSON
    def sendFromFileWithReplacement(msgfile, args, template=True):
        print("sendFromFileWithReplacement", msgfile)
        # Need casting?  Quick boolean fix
        if args[3].lower() == 'true':
            v = True
        elif args[3].lower() == 'false':
            v = False
        else:
            v = args[3]
        with open(msgfile) as json_file:
            msg = json.load(json_file)

        setParam(msg, args[2], v)
        # print(msg)
        return sendMessage(msg, template=template)


    # Threading OSC Server
    def handleOSC_UE(addr, *args):
        print("\n----- OSC in", datetime.today().strftime('%y-%m-%d %H:%M:%S'))
        print("  ", addr)
        if len(args) > 0:
            print("    k:", args[0])
            if len(args) > 1:
                print("    v:", args[1:])

                # TODO: Check for /xanadu/ue5/call

                if (args[0] == "sendFromFile"):
                    msgfile = os.path.join(messageRoot, args[1])
                    if not os.path.splitext(msgfile)[1]:
                        msgfile += '.json'
                    # TODO: Asynchronous queue
                    result = sendFromFile(msgfile)
                    jprint(result)

                if (args[0] == "sendFromFileWithReplacement"):
                    msgfile = os.path.join(messageRoot, args[1])
                    if not os.path.splitext(msgfile)[1]:
                        msgfile += '.json'
                    # TODO: Asynchronous queue, maybe use /remote/batch ?
                    result = sendFromFileWithReplacement(msgfile, args)
                    jprint(result)


    ## Experimental TCP support tested with QLab 5

    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        pass


    class ThreadedTCPRequestHandler(socketserver.BaseRequestHandler):
        def process(self, d):
            if len(d) == 0 or d == b'': return
            # print("handle tcp stream",d)
            try:
                msg = OscMessage(d)  # strip intro byte?
                dispatcher.call_handlers_for_packet(d, self.client_address)
            except Exception as e:
                print(str(e))

        def handle(self):
            data = b''
            log = b''
            self.request.settimeout(TCP_TIMEOUT)
            while True:
                try:
                    _data = self.request.recv(1024)  # accept until connection closed - need to handle streaming?
                    if not _data: break
                    data += _data
                    log += _data
                    msgs = data.split(b'\xc0')
                    if msgs[-1] == b'':  # ends with our delimeter
                        for msg in msgs: self.process(msg)
                        data = b''
                    else:
                        for msg in msgs[:-1]: self.process(msg)
                        data = msg + b'\xc0'  # more efficient way?
                except socket.timeout:
                    # print("tcp socket timeout")
                    break
                    #       data = data.strip()

            for msg in data.split(b'\xc0'):
                self.process(msg)

            print("\nfinished tcp {}:".format(self.client_address[0]), log)

    if not args.skipuecheck:
        print("---- Testing connectivity to UE")
        result = sendFromFile(os.path.join(internalMessageRoot,"checkConnectivity.json"),template=False)
        # TODO: Check for timeouts
        if result is not None:
            print("Successful")
        #jprint(result)

    if args.runosc is not None:
        oscargs = args.runosc.split(" ")
        handleOSC_UE (oscargs[0], *oscargs[1:])
        sys.exit(0)

    dispatcher = dispatcher.Dispatcher()
    dispatcher.map("/xanadu/ue5/*", handleOSC_UE)
    dispatcher.map("/xanadu/kl/*", handleOSC_KL)  # Kleroterion
    dispatcher.map("/xanadu/fb/put", handleOSC_FB)  # Generic firebase
    dispatcher.map("/xanadu/fb/post", handleOSC_FB)  # Generic firebase
    dispatcher.map("/xanadu/fb/delete", handleOSC_FB)  # Generic firebase
    dispatcher.map("/xanadu/fb/listen", handleOSC_FB_LISTEN)
    dispatcher.map("/xanadu/fb/removelisten", handleOSC_FB_LISTEN)

    from firebase import firebase
    firebase = firebase.FirebaseApplication('https://xanadu-f5762-default-rtdb.firebaseio.com', None)
    #print(firebase)

    # firebase listener
    # Run the listener in a separate thread
    listener_thread = threading.Thread(target=lambda: ref.listen(firebaseEventListener))
    print("Listening for firebase events")
    listener_thread.daemon = True
    listener_thread.start()

    #TCP OSC Server
    tcpserver = ThreadedTCPServer((oscServerHost, oscServerPort), ThreadedTCPRequestHandler)
    print("(Experimental) Awaiting tcp connections on {}".format(tcpserver.server_address))
    tcpserver_thread = threading.Thread(target=lambda: tcpserver.serve_forever())
    tcpserver_thread.start()



    udpserver = osc_server.ThreadingOSCUDPServer(
        (oscServerHost,oscServerPort), dispatcher)
    print("Awaiting OSC via udp on {}".format(udpserver.server_address))

    if args.gui:
        thread = threading.Thread(target=udpserver.serve_forever)
        thread.start()
    else:
        udpserver.serve_forever()


if (__name__=="__main__" and args.gui) or __name__=="__mp_main__":
    #ui.button('enlarge', on_click=lambda: app.native.main_window.resize(2000, 1500))
    ui.add_css('''
               .jse-theme-dark {
      --jse-theme: dark;

      /* over all fonts, sizes, and colors */
      --jse-theme-color: #2f6dd0;
      --jse-theme-color-highlight: #467cd2;
      --jse-background-color: #1e1e1e;
      --jse-text-color: #d4d4d4;
      --jse-text-color-inverse: #4d4d4d;

      /* main, menu, modal */
      --jse-main-border: 1px solid #4f4f4f;
      --jse-menu-color: #fff;
      --jse-modal-background: #2f2f2f;
      --jse-modal-overlay-background: rgba(0, 0, 0, 0.5);
      --jse-modal-code-background: #2f2f2f;

      /* tooltip in text mode */
      --jse-tooltip-color: var(--jse-text-color);
      --jse-tooltip-background: #4b4b4b;
      --jse-tooltip-border: 1px solid #737373;
      --jse-tooltip-action-button-color: inherit;
      --jse-tooltip-action-button-background: #737373;

      /* panels: navigation bar, gutter, search box */
      --jse-panel-background: #333333;
      --jse-panel-background-border: 1px solid #464646;
      --jse-panel-color: var(--jse-text-color);
      --jse-panel-color-readonly: #737373;
      --jse-panel-border: 1px solid #3c3c3c;
      --jse-panel-button-color-highlight: #e5e5e5;
      --jse-panel-button-background-highlight: #464646;

      /* navigation-bar */
      --jse-navigation-bar-background: #656565;
      --jse-navigation-bar-background-highlight: #7e7e7e;
      --jse-navigation-bar-dropdown-color: var(--jse-text-color);

      /* context menu */
      --jse-context-menu-background: #4b4b4b;
      --jse-context-menu-background-highlight: #595959;
      --jse-context-menu-separator-color: #595959;
      --jse-context-menu-color: var(--jse-text-color);
      --jse-context-menu-pointer-background: #737373;
      --jse-context-menu-pointer-background-highlight: #818181;
      --jse-context-menu-pointer-color: var(--jse-context-menu-color);

      /* contents: json key and values */
      --jse-key-color: #9cdcfe;
      --jse-value-color: var(--jse-text-color);
      --jse-value-color-number: #b5cea8;
      --jse-value-color-boolean: #569cd6;
      --jse-value-color-null: #569cd6;
      --jse-value-color-string: #ce9178;
      --jse-value-color-url: #ce9178;
      --jse-delimiter-color: #949494;
      --jse-edit-outline: 2px solid var(--jse-text-color);

      /* contents: selected or hovered */
      --jse-selection-background-color: #464646;
      --jse-selection-background-inactive-color: #333333;
      --jse-hover-background-color: #343434;
      --jse-active-line-background-color: rgba(255, 255, 255, 0.06);
      --jse-search-match-background-color: #343434;

      /* contents: section of collapsed items in an array */
      --jse-collapsed-items-background-color: #333333;
      --jse-collapsed-items-selected-background-color: #565656;
      --jse-collapsed-items-link-color: #b2b2b2;
      --jse-collapsed-items-link-color-highlight: #ec8477;

      /* contents: highlighting of search results */
      --jse-search-match-color: #724c27;
      --jse-search-match-outline: 1px solid #966535;
      --jse-search-match-active-color: #9f6c39;
      --jse-search-match-active-outline: 1px solid #bb7f43;

      /* contents: inline tags inside the JSON document */
      --jse-tag-background: #444444;
      --jse-tag-color: #bdbdbd;

      /* contents: table */
      --jse-table-header-background: #333333;
      --jse-table-header-background-highlight: #424242;
      --jse-table-row-odd-background: rgba(255, 255, 255, 0.1);

      /* controls in modals: inputs, buttons, and `a` */
      --jse-input-background: #3d3d3d;
      --jse-input-border: var(--jse-main-border);
      --jse-button-background: #808080;
      --jse-button-background-highlight: #7a7a7a;
      --jse-button-color: #e0e0e0;
      --jse-button-secondary-background: #494949;
      --jse-button-secondary-background-highlight: #5d5d5d;
      --jse-button-secondary-background-disabled: #9d9d9d;
      --jse-button-secondary-color: var(--jse-text-color);
      --jse-a-color: #55abff;
      --jse-a-color-highlight: #4387c9;

      /* svelte-select */
      --jse-svelte-select-background: #3d3d3d;
      --jse-svelte-select-border: 1px solid #4f4f4f;
      --list-background: #3d3d3d;
      --item-hover-bg: #505050;
      --multi-item-bg: #5b5b5b;
      --input-color: #d4d4d4;
      --multi-clear-bg: #8a8a8a;
      --multi-item-clear-icon-color: #d4d4d4;
      --multi-item-outline: 1px solid #696969;
      --list-shadow: 0 2px 8px 0 rgba(0, 0, 0, 0.4);

      /* color picker */
      --jse-color-picker-background: #656565;
      --jse-color-picker-border-box-shadow: #8c8c8c 0 0 0 1px;
    }''')

    msgfile="messages/test_sequence.json"
    with open(msgfile) as json_file:
        msg = json.load(json_file)

    editor = ui.json_editor({'readOnly':True, 'content': {'json': msg}}).classes(add='jse-theme-dark')
    editor.style('width:50%;height:75%;max-height:1000px;')
    ui.dark_mode(True)
    ui.run(native=True, dark=True, window_size=(1000, 800), fullscreen=False)


#
# # Load JSON file
# msgfile = "messages/test.json"
# with open(msgfile) as json_file:
#     msg = json.load(json_file)
#
# # fire request
# print(tsformat(datetime.now()), ">", url+msg["request"])
# jprint(msg["body"])
# headers = {'Content-Type': 'application/json'}
# r = requests.put(url+msg["request"], data=json.dumps(msg["body"]), headers=headers)
# print(tsformat(datetime.now()), "<", r.status_code, r.reason)
# jprint(json.loads(r.text))