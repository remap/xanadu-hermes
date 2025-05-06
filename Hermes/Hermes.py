# API -
# https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-api-http-reference-for-unreal-engine
#
# Example command line use to simulate osc command
# python ./Hermes.py -ueclient "192.168.1.180:30010" -runosc "/xanadu/ue5/call sendFromFileWithReplacement test.json bNewVisibility true"

# Note that our messages require generateTransaction:true to propagate in multiuser editor, I think.
import shlex
import requests    # pip install requests
from pythonosc import dispatcher, osc_server   # pip install python-osc
from pythonosc.osc_message import OscMessage
import json
import argparse
import os, sys
from datetime import datetime, timedelta
import threading
from pathlib import Path
#from nicegui import app, ui
import socketserver, socket

from hermes.utils import ColorFormatter, reviseTemplateForPIE, jformat, setParam, splitInstanceHostPort, splitHostPort
from hermes.ue.UEClient import UEClient
from hermes.fb.anonclient import FBAnonClient

from fastapi import FastAPI, Request
from pydantic import BaseModel

UE_JSON_PKG_PATH = True  # enable   a.b.c => a/b/c for sendFile
UE_JSON_PKG_PATH_DEFAULT = "_default.json"  # use this if path resolves to director

import logging
import logging.config


if __name__=="__main__":

    # Setup logger
    path = Path("logconfig.json")
    with path.open("r", encoding="utf-8") as f:
        logconfig = json.load(f)
    logging.config.dictConfig(logconfig)
    logger = logging.getLogger("main")
    logger.setLevel(logging.DEBUG)

    # Use argparse to handle command line arguments
    parser = argparse.ArgumentParser(description='Send a command to Unreal Engine via Remote Control API')
    parser.add_argument('-ueclient', type=str, help='unreal client host:port', default=None)
    parser.add_argument('-ispie', action='store_true', help='ueclient is pie')
    parser.add_argument('-uemulticlient', type=str, help='load unreal clients from config file', default=None)
    parser.add_argument('-oscserver', type=str, help='OSC server host:port', default="0.0.0.0:8000")
    parser.add_argument('-skipuecheck', action='store_true', help='Skip checking for ue connectivity first')
    parser.add_argument('-skipuenamemap', action='store_true', help='Skip Mapping names')
    parser.add_argument('-instance', required=False, type=str, help='instance name, will override template value')
    parser.add_argument('-template', required=False, type=str, help='template file')
    parser.add_argument('-messagedir', required=False, type=str, help='message folder', default="messages")
    parser.add_argument('-paramdir', required=False, type=str, help='message folder')
    parser.add_argument('-gui',action='store_true',help='experimental gui')
    parser.add_argument('-runosc', type=str)
    args = parser.parse_args()

    ## fb namespace
    instance = args.instance

    # todo: move to config
    default_listeners = [
        {"addr": f"/{instance}/ch/cue/ch1",
         "args": "listenForCh1"},
        {"addr": f"/{instance}/ch/cue/ch2",
         "args": "listenForCh2"},
        {"addr": f"/{instance}/ch/cue/ch2-siren",
         "args": "listenForCh2-siren"},
        {"addr": f"/{instance}/ch/cue/ch3",
         "args": "listenForCh3"}
    ]

    ## OSC
    (oscServerHost, oscServerPort) = splitHostPort(args.oscserver)

    ##  Message files
    messageRoot = args.messagedir
    paramRoot = args.messagedir if args.paramdir is None else args.paramdir
    internalMessageRoot = os.path.join("messages", "_internal")

    ## variables
    from hermes.template import Template
    if args.template is not None:
        tpl = Template.from_json_file(args.template)
        if instance is not None: tpl.add("instance",instance)
        logger.info(f"Template variables from {args.template}")
        logger.debug(jformat(tpl.mapping))
        instance = tpl["instance"]  # for legacy code
        #instance = tpl["i"]  # for legacy code

        #        logger.info(jformat(tpl.mapping)) # should not expose?
        prefix = tpl["prefix"] # also legacy
    else:
        tpl=None
        logger.warning("No template file specified!")

    logger.info(f"Instance: {instance}")
    logger.info(f"Firebase namespace (instance): /{instance}")
    logger.info(f"OSC Server: {oscServerHost}:{oscServerPort}")
    logger.info(f"Message file root: {messageRoot}")


    ## UE5
    ueclient = {}



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
            mapNames=True
            if "mapNames" in data[ueInstance]:
                if data[ueInstance]["mapNames"]==False: mapNames=False

            ueURL = "http://" + data[ueInstance]["host"] + ":" + str(data[ueInstance]["port"])
            logger.info(f"UE ({ueInstance}) client on {data[ueInstance]['host']}:{data[ueInstance]['port']}")
            #print(f"UE ({ueInstance}) Path Prefix:", data[ueInstance]["prefix"])

            newtpl = tpl.copy() #fix extra copy?
            ispie=False
            if "isPIE" in data[ueInstance] and data[ueInstance]["isPIE"] and "_pie" in newtpl:
                ispie=True
                reviseTemplateForPIE(newtpl)
                logger.info(f"Revised template for PIE {newtpl['world']}, {newtpl['prefix']}")
                logger.debug(jformat(newtpl.mapping))
            #print(newtpl)
            ueclient[ueInstance] = UEClient(ueurl=ueURL, instance=ueInstance, prefix=prefix, template=newtpl,
                                            internalMessageRoot=internalMessageRoot, paramRoot=paramRoot, connectivityCheck=check, isPIE=ispie, mapNames=mapNames)

    # use instance "any" to send any instance to an output
    # Single instance from command line (legacy)
    if args.ueclient is not None:
        (ueInstance, ueClientHost, ueClientPort) = splitInstanceHostPort(args.ueclient)
        if ueInstance in ueclient:
            logger.warning("Command line overriding multiclient")
        ueURL = "http://" + ueClientHost + ":" + str(ueClientPort)

        logger.info(f"UE ({ueInstance}) client on {ueClientHost}:{ueClientPort}")
        #print(f"UE ({ueInstance}) Path Prefix:", prefix)

        newtpl = tpl.copy()
        ispie=False
        if args.ispie is not None:
            ispie=True
            reviseTemplateForPIE(newtpl)
            logger.info(f"Revised template for PIE {newtpl['world']}, {newtpl['prefix']}")
            logger.debug(jformat(newtpl.mapping))
        #print(newtpl)
        ueclient[ueInstance] = UEClient( ueurl=ueURL, instance=ueInstance,prefix=prefix, template=newtpl,
                                         internalMessageRoot=internalMessageRoot, paramRoot=paramRoot, connectivityCheck=True, isPIE=ispie, mapNames=True)



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
    listenPath = f"/{instance}/ch"
    logger.info(f"Firebase listener root: {listenPath}" )
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
            logger.info(f"Suppressing initial firebase message ")#{e}")
        else:
            logger.info(f"firebase event {e}")
            #ogger.debug(f"{path}")
            for lp in fblisteners.keys():
                if not path.startswith(lp): continue
                for k,v in fblisteners[lp].items():
                    logger.debug(f"{k},{v}")
                    # TODO: Validate
                    if v["action"]["type"].lower() == "echo":
                        logger.debug("echo=>" + v["action"]["data"].format(path=path,value=event.data))
                    if v["action"]["type"].lower() == "unreal":
                        logger.debug("unreal=>")
                        target = "*" if "target" not in v["action"] else v["action"]["target"]  # default to all
                        if not isinstance(target, list): target = [target]
                        # TODO: Repeated from call - fix
                        ueclientset = set(ueclient)
                        targets = set(target)
                        sendToAll = "*" in targets
                        haveAny = "any" in ueclient
                        haveAtLeastOne = targets & ueclientset
                        missing = targets - ueclientset
                        if len(missing) > 0:
                            logger.error(f"No available target: {missing}")



                        if "parsing" in v:
                            if v["parsing"]["type"] == "glom":
                                #print("glom")
                                spec=Assign(v["parsing"]["spec"], event.data)
                                _ = glom(v, spec)
                            if v["parsing"]["type"] == 'external_params':
                                try:
                                    if isinstance(event.data, str):
                                        v["action"]["data"]["externalParams"] = json.loads(event.data)
                                        logger.debug(f"Parsed JSON: {v["action"]["data"]["externalParams"]}")
                                    else: #dict
                                        v["action"]["data"]["externalParams"] = event.data
                                        logger.debug(f"Got JSON: {v["action"]["data"]["externalParams"]}")
                                except:
                                    logger.error(f"fblistener problem loading external params JSON {event.data}")
                        logger.debug(jformat(v["action"]["data"]))
                        for ueInstance in ueclient:
                            # any always sends
                            if ueInstance == "any" or ueInstance in targets or sendToAll:
                                    ueclient[ueInstance].sendMessage(msgs=[v["action"]["data"]], applyTemplates=True)  # TODO NEED TO ITERATE!
        fbmsg+= 1

    # Firebase
    # put interface ... uses firebase simplified client library
    #
    global TCP_TIMEOUT
    TCP_TIMEOUT = 0.15
    # tradeoff here is possibility of dropping data during congestion
    # really we should be streaming out commands as they come in.
    #

    def fb_callback(result, source=None):
        logger.info(f"Firebase async return from {source}: {result}")

    def osc_addr_template(s):
        return s.replace("{{instance}}", instance)

    import re
    def handleOSC_KL(addr, *args):
        addr = osc_addr_template(addr)


        if len(args) > 1:
            # Schedmessage templating
            if (args[0]=="schedmessage" and args[1].startswith("{{")):
                now = datetime.now()
                args = list(args)
                #print("    v:", args[1:])
                pattern = r"\{\{([0-9.]+)\}\}"
                n = float(re.search(pattern, args[1]).group(1))
                future_time = now + timedelta(milliseconds=n)
                args[1] = future_time.strftime('%H:%M:%S.%f')[:-3]
            logger.info(f"OSC KL {addr} k: {args[0]} v: {args[1:]}")
        else:
            logger.info(f"OSC KL {addr} k: {args[0]}")
        #print("    v:", args[1:])

        result = []
        if (addr).endswith("/kvproperty"):
            if (len(args) % 2) == 1:
                logger.warning("OSC KL setting trailing null value to empty string")
                args = list(args).append("")
            for i in range(0, len(args), 2):
                logger.debug(f"     {args[i]} {args[i + 1]}")
                firebase.put_async(addr, args[i], args[i + 1], params={'print': 'pretty'},
                                   headers={'X_FANCY_HEADER': 'VERY FANCY'}, callback=lambda result: fb_callback(result, f"{args[1:]}"))
        else:  # if (addr).endswith("/method") or (addr).endswith("/childmethod") or (addr).endswith("/event"):
            result = firebase.post_async(addr, args, params={'print': 'pretty'},
                                         headers={'X_FANCY_HEADER': 'VERY FANCY'}, callback=lambda result: fb_callback(result, f"{args[1:]}"))
    def handleOSC_FB(addr, *args):
        addr = osc_addr_template(addr)
        if len(args) > 1:
            logger.info(f"OSC FB {addr} k: {args[0]} v: {args[1:]}")
        else:
            logger.info(f"OSC FB {addr} k: {args[0]}")

        result = []
        if (addr).endswith("/put"):
            if (len(args) % 2) == 0:
                logger.warning("OSC FB setting trailing null value to empty string")
                args = list(args).append("")
            for i in range(1, len(args), 2):
                logger.debug(f"     {args[i]} {args[i + 1]}")
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
        logger.info(f"OSC FB_LISTEN {addr} k: {args[0]}")
        if (addr).endswith("/listen"):
            logger.debug(f"listen {args[0]} {args[1]}")
            # TODO: Validate args
            msgfile = os.path.join(messageRoot, args[1])
            if not os.path.splitext(msgfile)[1]:
                msgfile += '.json'
            with open(msgfile) as json_file:
                msg = json.load(json_file)
            if not args[0] in fblisteners:
                fblisteners[args[0]] = {}
            fblisteners[args[0]][msgfile] = msg  # TODO: Wrap to hold the client
            logger.debug(f"fblisteners {fblisteners}")
        elif (addr).endswith("/removelisten"):
            logger.debug(f"removelisten {args[0]} {args[1]}")
            msgfile = os.path.join(messageRoot, args[1])
            if not os.path.splitext(msgfile)[1]:
                msgfile += '.json'
            if args[0] in fblisteners:
                fblisteners[args[0]].pop(msgfile, None)
                if len(fblisteners[args[0]])==0:
                    fblisteners.pop(args[0], None)
            else:
                logger.warning(f"fblisteners nothing to remove, {args[0]}")
            logger.debug(f"fblisteners: {fblisteners}")


    # Threading OSC Server
    def handleOSC_UE(addr, *args):
        addrcomps = addr.split("/")
        verb = addrcomps[-1]

        if len(args) < 1 and verb !="mapnames" and verb !="mapnamesglobal" and verb != "mapnamesglobalpie":
            logger.error(f"OSC UE < {addr} not enough args {args}")
            return
        ueclientset = set(ueclient)
        targets = set(addrcomps[-2].split(","))
        sendToAll = "*" in targets
        haveAny = "any" in ueclient
        haveAtLeastOne = targets & ueclientset
        missing = targets - ueclientset
        if len(missing) > 0:
            logger.error(f"No available target: {missing}" )
        noSubName = "ue5" in targets
        if (noSubName and not haveAny) or (not haveAtLeastOne and not sendToAll):
            logger.error(f"No available instance for namespace {addr}")
            return

        dumpmap = False
        if verb=="mapnames":
            logger.info(f"OSC UE < mapnames {args}")  # \n\tk: {args[0]}\n\tv: {args[1:]}")
            if "dump" in args: dumpmap = True
        elif verb=="mapnamesglobal":
            logger.info(f"OSC UE < mapnamesglobal {args}")  # \n\tk: {args[0]}\n\tv: {args[1:]}")
            if "dump" in args: dumpmap = True
        elif verb == "mapnamesglobalpie":
            logger.info(f"OSC UE < mapnamesglobalpie {args}")  # \n\tk: {args[0]}\n\tv: {args[1:]}")
            if "dump" in args: dumpmap = True
        elif verb=="call":
            logger.info(f"OSC UE < call {args[0]}")  # \n\tk: {args[0]}\n\tv: {args[1:]}")
        elif verb=="call_generic":
            logger.info(f"OSC UE < call_generic {args}")  # \n\tk: {args[0]}\n\tv: {args[1:]}")
        elif verb == "call_delegate":
            logger.info(f"OSC UE < call_delegate {args}")  # \n\tk: {args[0]}\n\tv: {args[1:]}")
        else:
            logger.error(f"OSC UE unknown verb {verb}")
            return

        templates = []
        msgFileArg = ""
        params = None
        if len(args) >= 1:
            if verb == "call_generic" or verb=="call_delegate":
                cg_template = Template({"_object": args[0], "_function": args[1], "_transaction": True})
                templates.append(cg_template)
                args = args[2:]
            elif verb == "call":
                msgFileArg = args[0]
                args = args[1:]
            # regular call parsing
            if (len(args) % 2 != 0): logger.warning("OSC UE odd number of kv pairs, one will be dropped from var parsing")
            pairs = dict(zip(*[iter(args)] * 2))
            templates.append(Template(pairs))
            if verb=="call_generic" or verb=="call_delegate":
                params = pairs
                logger.debug(f"Call generic {cg_template} {params}")
            logger.debug(f"OSC UE parsing dynamic vars:{[str(t) for t in templates]}")

        # Loop through the clients and do the work
        for ueInstance in ueclient:
            # any always sends
            if ueInstance=="any" or ueInstance in targets or sendToAll:
                uec = ueclient[ueInstance]
                if verb=="call": #(args[0] == "sendFromFile"):
                    msgfile = os.path.join(messageRoot, msgFileArg)
                if verb=="call_generic":
                    msgfile = os.path.join(internalMessageRoot, "callGeneric")
                if verb == "call_delegate":
                    msgfile = os.path.join(internalMessageRoot, "callDelegate")
                if verb=="call" or verb=="call_generic" or verb=="call_delegate":
                    if UE_JSON_PKG_PATH:
                        msgfile = msgfile.replace(".", os.sep)
                        if os.path.isdir(msgfile) and UE_JSON_PKG_PATH:
                             msgfile = os.path.join(msgfile, UE_JSON_PKG_PATH_DEFAULT)
                    if not os.path.splitext(msgfile)[1]:
                        msgfile += '.json'

                    # Now, async so no real return here
                    #(rc,result) = (
                    uec.sendFromFile(msgfile, suppressBodyPrint=False, applyTemplates=True, templates=templates, params=params) #)
                elif verb=="mapnames":
                    uec.getNameMap(dump=dumpmap, force=True)
                elif verb == "mapnamesglobal":
                    uec.getNameMap(dump=dumpmap, force=True, useGlobal=True)
                elif verb == "mapnamesglobalpie":
                    uec.getNameMap(dump=dumpmap, force=True, useGlobal=True, usePIE=True)
                    # (rc, result) = uec.sendFromFile(os.path.join(internalMessageRoot,"dumpActorNameMap.json"), suppressBodyPrint=True, applyTemplates=True,
                    #                                 templates=templates)
                    # if result is not None:
                    #     try:
                    #         map = json.loads(result[0]["ReturnValue"])
                    #         if dumpmap: logger.debug(jformat(map))
                    #         logger.info(f"Loaded {len(map)} name maps.")
                    #         uec.setActorTemplate(Template(map))
                    #     except: # TODO: Fix exception detail
                    #         logger.error("Exception in loading map")
                    #     # log in uec
                        #logger.info(jformat(result))

                    # if (args[0] == "sendFromFileWithReplacement"):
                    #     msgfile = os.path.join(messageRoot, args[1])
                    #     if not os.path.splitext(msgfile)[1]:
                    #         msgfile += '.json'
                    #     # TODO: Asynchronous queue, maybe use /remote/batch ?
                    #     (rc,result) = uec.sendFromFileWithReplacement(msgfile, args)
                    #     jprint(result)


    for ueInstance in ueclient:
        if not args.skipuecheck:
            ueclient[ueInstance].checkConnection()
        if not args.skipuenamemap:
            ueclient[ueInstance].getNameMap()

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

    # Anon client with token renewal
    fbclient = FBAnonClient(credentialFile="xanadu-secret-f5762-firebase-adminsdk-9oc2p-1fb50744fa.json", dbURL='https://xanadu-f5762-default-rtdb.firebaseio.com')
    firebase = fbclient.getFB()

    # firebase listener
    # Run the listener in a separate thread
    listener_thread = threading.Thread(target=lambda: ref.listen(firebaseEventListener), daemon=True)
    logger.info("Listening for firebase events")
    listener_thread.daemon = True
    listener_thread.start()

    from fastapi import FastAPI, HTTPException, Depends
    from pydantic import BaseModel
    from threading import Thread
    from uvicorn import Config, Server
    from fastapi.staticfiles import StaticFiles
    from pythonosc import osc_message_builder
    from starlette.responses import Response
    uvicorn_logger = logger
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    class EmbeddedFastAPIServer:
        def __init__(self, host="127.0.0.1", port=4242, logger=None):
            self.logger = logger
            self.app = FastAPI()
            self.app.add_middleware(
                TrustedHostMiddleware, allowed_hosts=["127.0.0.1"]
            )
            self.host = host
            self.port = port
            self.server_thread = None

            self.config = Config(app=self.app, host=self.host, port=self.port, log_level="warning")
            self.server = Server(config=self.config)
            self.static_site = "osceditor"
            self.persistFile = "osceditor-persist.txt"
            self._configure_routes()

            # for route in self.app.routes:
            #     try:
            #         print(f"Path: {route.path}, Methods: {route.methods}, Name: {route.name}")
            #     except:
            #         pass
            #


        def _configure_routes(self):
            # Define request model
            class LineRequest(BaseModel):
                line: int
                content: str

            ## Process incoming osc
            ##
            @self.app.post("/process-osc")
            async def process_osc(request: LineRequest):
                #processed_content = request.content.upper()
                if len(request.content) == 0 : return
                msg = None
                try:
                    #args = request.content.strip().split(" ")
                    args = shlex.split( request.content.strip() )
                    self.logger.info(f"Web interface received: {args}")
                    builder = osc_message_builder.OscMessageBuilder(address=args[0])
                    for arg in args[1:]:
                        builder.add_arg(arg)
                    msg = builder.build()
                    d = msg.dgram
                    if len(d) == 0 or d == b'': return
                    dispatcher.call_handlers_for_packet(d, ("127.0.0.1",4242))
                except Exception as e:
                    logger.error(str(e))
                return {
                    "line": request.line,
                    "original": request.content,
                    "processed": str(msg),
                }


            # Endpoint to load file content
            @self.app.get("/load-file")
            async def load_file():
                if not os.path.exists(self.persistFile):
                    raise HTTPException(status_code=404, detail="File not found.")
                with open(self.persistFile, "rb") as f:
                    content = f.read()
                return {"content": content}

            # Endpoint to save file content
            @self.app.post("/save-file")
            async def save_file(request: Request):

                content = await request.body()  # Read raw text body
                print(content)
                try:
                    with open(self.persistFile, "wb") as f:
                        f.write(content)
                    return {"message": "File saved successfully."}
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

            ## Serve our index file
            ##
            if os.path.exists(self.static_site):
                self.app.mount("/", StaticFiles(directory=self.static_site, html=True), name="static")
            else:
                raise FileNotFoundError(f"Static file '{self.static_site}' not found.")



        def _run_server(self):
            # Uvicorn Server (run in the thread)
            self.server.run()

        def start(self):
            if self.server_thread is None:
                self.server_thread = Thread(target=self._run_server, daemon=True)
                self.server_thread.start()
                print(f"FastAPI server started at http://{self.host}:{self.port}")

        def stop(self):
            if self.server.started and self.server.should_exit is False:
                self.server.should_exit = True
                print("FastAPI server stopped.")


    # Create the server instance
    server = EmbeddedFastAPIServer(host="127.0.0.1", port=4242, logger=logger)

    # Start the server in a separate thread
    server.start()


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
                logger.error(str(e))

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
                        data = msg + b'\xc0'
                except socket.timeout:
                    # print("tcp socket timeout")
                    break
                    #       data = data.strip()
                except Exception as e:
                    logger.error(f"Error in TCP  {self.client_address[0]}", exc_info=True)
                    break

            for msg in data.split(b'\xc0'):
                try:
                    self.process(msg)
                except:
                    logger.error(f"Error in message processing {self.client_address[0]}", exc_info=True)
                    return

            logger.debug(f"finished tcp {self.client_address[0]}:\n{log}")

    #TCP OSC Server
    tcpserver = ThreadedTCPServer((oscServerHost, oscServerPort), ThreadedTCPRequestHandler)
    logger.info(f"(Experimental) Awaiting tcp connections on {tcpserver.server_address}")
    tcpserver_thread = threading.Thread(target=lambda: tcpserver.serve_forever(), daemon=True)
    tcpserver_thread.start()

    udpserver = osc_server.ThreadingOSCUDPServer(
        (oscServerHost,oscServerPort), dispatcher)
    logger.info(f"Awaiting OSC via udp on {udpserver.server_address}")

    for L in default_listeners:
        handleOSC_FB_LISTEN(L["addr"], L["args"])

    thread=None
    if args.gui:
        thread = threading.Thread(target=udpserver.serve_forever,daemon=True)
        thread.start()
    else:
        try:
            udpserver.serve_forever()
        except KeyboardInterrupt:
            logging.info("Caught keyboard interrupt")
            os._exit(0)  # TODO: Graceful exit.


if (__name__=="__main__" and args.gui) or __name__=="__mp_main__":
    pass
    # from hermes.gui.theme import dark_theme
    # ui.add_css(dark_theme)
    #
    # msgfile="messages/test_sequence.json"
    # with open(msgfile) as json_file:
    #     msg = json.load(json_file)
    #
    # editor = ui.json_editor({'readOnly':True, 'content': {'json': msg}}).classes(add='jse-theme-dark')
    # editor.style('width:50%;height:75%;max-height:1000px;')
    # ui.dark_mode(True)
    # ui.run(native=True, dark=True, window_size=(1000, 800), fullscreen=False)
    #
