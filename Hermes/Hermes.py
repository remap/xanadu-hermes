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
from datetime import datetime, timedelta
import threading
from pathlib import Path
from nicegui import app, ui

import socketserver, socket


from hermes.utils import jprint, tsformat, setParam, splitInstanceHostPort, splitHostPort
from hermes.ue.UEClient import UEClient

UE_JSON_PKG_PATH = True  # enable   a.b.c => a/b/c for sendFile
UE_JSON_PKG_PATH_DEFAULT = "_default.json"  # use this if path resolves to director


if __name__=="__main__":

    # Use argparse to handle command line arguments
    parser = argparse.ArgumentParser(description='Send a command to Unreal Engine via Remote Control API')
    parser.add_argument('-ueclient', type=str, help='unreal client host:port', default=None)
    parser.add_argument('-uemulticlient', type=str, help='load unreal clients from config file', default=None)
    parser.add_argument('-oscserver', type=str, help='OSC server host:port', default="0.0.0.0:8000")
    parser.add_argument('-skipuecheck', action='store_true', help='Skip checking for ue connectivity first')
    parser.add_argument('-instance', required=False, type=str, help='instance name, will override template value')
    parser.add_argument('-template', required=False, type=str, help='template file')
    parser.add_argument('-messagedir', required=False, type=str, help='message folder', default="messages")
    parser.add_argument('-gui',action='store_true',help='experimental gui')
    parser.add_argument('-runosc', type=str)
    args = parser.parse_args()

    ## fb namespace
    instance = args.instance

    ## OSC
    (oscServerHost, oscServerPort) = splitHostPort(args.oscserver)


    # prefix_editor = "/Game/_Sets/Xanadu_Fall24_v001/"
    # prefix_PIE = "/Game/_Sets/Xanadu_Fall24_v001/UEDPIE_0_"
    # prefix = prefix_PIE
    #


    ##  JSON
    messageRoot = args.messagedir
    internalMessageRoot = os.path.join("messages", "_internal")

    ## variables
    from hermes.template import Template
    if args.template is not None:
        tpl = Template.from_json_file(args.template)
        if instance is not None: tpl.add("instance",instance)
        print(f"Template variables from {args.template}")
        instance = tpl["instance"]  # for legacy code
        jprint(tpl.mapping)  # should not expose?
        prefix = tpl["prefix"] # also legacy

    else:
        tpl=None
        print("No template file specified!")

    print("Instance:", instance)

    print("-------")
    print("Firebase namespace (instance): /" + instance)
    print("OSC Server:", oscServerHost, oscServerPort)
    print("Message file root:", messageRoot)


    ## UE5
    ueclient = {}

    def reviseTemplateForPIE(newtpl):
        if "world" in newtpl:
            parts = newtpl["world"].rsplit("/", 1)
            parts[-1] = newtpl["pie"] + parts[-1]
            newtpl["world"] = "/".join(parts)
        if "prefix" in newtpl:
            newtpl["prefix"] += newtpl["pie"]
        print("Revised template for PIE", newtpl["world"], newtpl["prefix"])

    if args.uemulticlient is not None:
        path = Path(args.uemulticlient)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for ueInstance in data:

            # whether to process at all
            if "load" in data[ueInstance]:
                if data[ueInstance]["load"]==False: continue

            #connectivity check
            check=True
            if "check" in data[ueInstance]:
                if data[ueInstance]["check"]==False: check=False

            ueURL = "http://" + data[ueInstance]["host"] + ":" + str(data[ueInstance]["port"])
            print(f"UE ({ueInstance}) client on {data[ueInstance]['host']}:{data[ueInstance]['port']}")
            #print(f"UE ({ueInstance}) Path Prefix:", data[ueInstance]["prefix"])

            newtpl = tpl.copy() #fix extra copy?
            if "isPIE" in data[ueInstance] and data[ueInstance]["isPIE"] and "pie" in newtpl:
                reviseTemplateForPIE(newtpl)
            #print(newtpl)
            ueclient[ueInstance] = UEClient(ueurl=ueURL, instance=ueInstance, prefix=prefix, template=newtpl,
                                            internalMessageRoot=internalMessageRoot, connectivityCheck=check)

    # use instance "any" to send any instance to an output
    # Single instance from command line (legacy)
    if args.ueclient is not None:
        (ueInstance, ueClientHost, ueClientPort) = splitInstanceHostPort(args.ueclient)
        if ueInstance in ueclient:
            print("** Warning: command line overriding multiclient")
        ueURL = "http://" + ueClientHost + ":" + str(ueClientPort)

        print(f"UE ({ueInstance}) client on {ueClientHost}:{ueClientPort}")
        #print(f"UE ({ueInstance}) Path Prefix:", prefix)

        newtpl = tpl.copy()
        if "isPIE" in data[ueInstance] and data[ueInstance]["isPIE"] and "pie" in newtpl:
            reviseTemplateForPIE(newtpl)
        #print(newtpl)
        ueclient[ueInstance] = UEClient( ueurl=ueURL, instance=ueInstance,prefix=prefix, template=newtpl,
                                         internalMessageRoot=internalMessageRoot, connectivityCheck=True)



    # Firebase event listener
    # Uses firebase-admin library

    import firebase_admin
    from firebase_admin import credentials, db  # pip install firebase-admin
    with open("xanadu-secret-firebase-forwarder.json") as f:
        firebase_config = json.load(f)
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
                        ueclient.sendMessage(v["action"]["data"], template=True)
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

    def osc_addr_template(s):
        return s.replace("{{instance}}", instance)

    import re
    def handleOSC_KL(addr, *args):
        print("\n-KL--", datetime.today().strftime('%y-%m-%d %H:%M:%S'))
        addr = osc_addr_template(addr)
        print("  ", addr)
        print("    k:", args[0])
        if len(args) > 1:
            # Schedmessage templating
            if (args[0]=="schedmessage" and args[1].startswith("{{")):
                now = datetime.now()
                args = list(args)
                print("    v:", args[1:])
                pattern = r"\{\{([0-9.]+)\}\}"
                n = float(re.search(pattern, args[1]).group(1))
                future_time = now + timedelta(milliseconds=n)
                args[1] = future_time.strftime('%H:%M:%S.%f')[:-3]
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
        addr = osc_addr_template(addr)
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


    # Threading OSC Server
    def handleOSC_UE(addr, *args):
        print("\n----- OSC <", datetime.today().strftime('%y-%m-%d %H:%M:%S'))
        print("  ", addr)
        addrcomps = addr.split("/")
        if len(args) > 0:
            print("    k:", args[0])
            if len(args) > 1:
                print("    v:", args[1:])


                # TODO: Check for /xanadu/ue5/call
                templates = []
                if len(args) > 2:
                    if (len(args[2:]) % 2 != 0): print("    Warning: odd number of kv pair, one will be dropped from templating")
                    pairs = dict(zip(*[iter(args[2:])] * 2))
                    templates.append(Template(pairs))
                    print("    templates:", [str(t) for t in templates])

                for ueInstance in ueclient:
                    # any always sends

                    if ueInstance=="any" or ueInstance == addrcomps[-2]:
                        uec = ueclient[ueInstance]
                        if (args[0] == "sendFromFile"):
                            msgfile = os.path.join(messageRoot, args[1])
                            if UE_JSON_PKG_PATH:
                                msgfile = msgfile.replace(".", os.sep)
                                if os.path.isdir(msgfile) and UE_JSON_PKG_PATH:
                                     msgfile = os.path.join(msgfile, UE_JSON_PKG_PATH_DEFAULT)
                            if not os.path.splitext(msgfile)[1]:
                                msgfile += '.json'
                            # TODO: Asynchronous queue
                            (rc,result) = uec.sendFromFile(msgfile, suppressBodyPrint=False, applyTemplates=True, templates=templates)
                            jprint(result)

                        # if (args[0] == "sendFromFileWithReplacement"):
                        #     msgfile = os.path.join(messageRoot, args[1])
                        #     if not os.path.splitext(msgfile)[1]:
                        #         msgfile += '.json'
                        #     # TODO: Asynchronous queue, maybe use /remote/batch ?
                        #     (rc,result) = uec.sendFromFileWithReplacement(msgfile, args)
                        #     jprint(result)


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
        for ueInstance in ueclient:
            ueclient[ueInstance].checkConnection()

    if args.runosc is not None:
        oscargs = args.runosc.split(" ")
        handleOSC_UE (oscargs[0], *oscargs[1:])
        sys.exit(0)

    # Listen for both our specific instance and the template placeholder
    #
    dispatcher = dispatcher.Dispatcher()
    dispatcher.map(f"/{instance}/ue5/*", handleOSC_UE)
    dispatcher.map(f"/{instance}/kl/*", handleOSC_KL)  # Kleroterion
    dispatcher.map(f"/{instance}/fb/put", handleOSC_FB)  # Generic firebase
    dispatcher.map(f"/{instance}/fb/post", handleOSC_FB)  # Generic firebase
    dispatcher.map(f"/{instance}/fb/delete", handleOSC_FB)  # Generic firebase
    dispatcher.map(f"/{instance}/fb/listen", handleOSC_FB_LISTEN)
    dispatcher.map(f"/{instance}/fb/removelisten", handleOSC_FB_LISTEN)
    dispatcher.map("/{{instance}}/ue5/*", handleOSC_UE)
    dispatcher.map("/{{instance}}/kl/*", handleOSC_KL)  # Kleroterion
    dispatcher.map("/{{instance}}/fb/put", handleOSC_FB)  # Generic firebase
    dispatcher.map("/{{instance}}/fb/post", handleOSC_FB)  # Generic firebase
    dispatcher.map("/{{instance}}/fb/delete", handleOSC_FB)  # Generic firebase
    dispatcher.map("/{{instance}}/fb/listen", handleOSC_FB_LISTEN)
    dispatcher.map("/{{instance}}/fb/removelisten", handleOSC_FB_LISTEN)

    from firebase.firebase import firebase as _firebase



#https://firebase.google.com/docs/database/rest/auth#python
    import google
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    import uuid

    # Define the required scopes
    scopes = [
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/firebase.database"
    ]

    # Authenticate a credential with the service account
    credentials = service_account.Credentials.from_service_account_file(
        "xanadu-secret-f5762-firebase-adminsdk-9oc2p-1fb50744fa.json", scopes=scopes)
    # Use the credentials object to authenticate a Requests session.
    # authed_session = AuthorizedSession(credentials)
    # response = authed_session.get(
    #     "https://<DATABASE_NAME>.firebaseio.com/users/ada/name.json")

    # Or, use the token directly, as described in the "Authenticate with an
    # access token" section below. (not recommended)

    # this lib uses rest calls
    firebase = _firebase.FirebaseApplication('https://xanadu-f5762-default-rtdb.firebaseio.com')
    uid = uuid.uuid4()
    def refresh_fb_token(firebase, uid):
        # Refresh the token
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        access_token = credentials.token
        expiration_time = credentials.expiry.astimezone()
        # Print the token and expiration time in local timezone
        print(f"Refresh FB Access Token:")
        print(f"\tToken: {access_token[0:25]}...")
        print(f"\tExpiry: {expiration_time}")
        firebase.setAccessToken(access_token)
        # Schedule the next refresh in 1 hour
        threading.Timer(3600, refresh_fb_token, args=[firebase, uid]).start()
    # Start the first refresh
    refresh_fb_token(firebase, uid)

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
    from hermes.gui.theme import dark_theme
    ui.add_css(dark_theme)

    msgfile="messages/test_sequence.json"
    with open(msgfile) as json_file:
        msg = json.load(json_file)

    editor = ui.json_editor({'readOnly':True, 'content': {'json': msg}}).classes(add='jse-theme-dark')
    editor.style('width:50%;height:75%;max-height:1000px;')
    ui.dark_mode(True)
    ui.run(native=True, dark=True, window_size=(1000, 800), fullscreen=False)

