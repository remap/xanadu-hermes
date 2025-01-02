# Replace a specific parameter
# setParam(msg, "bNewVisibility", True if args.value.lower() in ('true') else False)
import json
import requests
import os
from datetime import datetime, timedelta
from hermes.utils import tsformat, jprint

class UEClient:

    def __init__(self, ueurl, instance=None, prefix=None, template=None, internalMessageRoot=None):
        self.ueurl = ueurl
        self.instance = instance
        self.prefix = prefix
        self.template = template
        self.internalMessageRoot = internalMessageRoot

    def sendMessage(self, msgs, template=False, suppressBodyPrint = False):
        url = self.ueurl
        result = []
        if not isinstance(msgs, list):
            msgs = [msgs]

        for msg in msgs:
            # TODO: Should send return codes back
            print(f"UE ({self.instance})", tsformat(datetime.now()), ">", url + msg["request"])
            if "body" in msg:
                headers = {'Content-Type': 'application/json'}
                if template:
                    # Legacy
                    if "objectPath" in msg["body"]: msg["body"]["objectPath"] = msg["body"]["objectPath"].replace(
                        "{{prefix}}", self.prefix)
                    msg = self.template.replace_in_dict(msg)
                if not suppressBodyPrint: jprint(msg["body"])
                data = json.dumps(msg["body"])
            else:
                headers = None
                data = None
            r=None
            if "method" in msg:
                if msg["method"] == "get":
                    r = requests.get(url + msg["request"], data=data, headers=headers)
                if msg["method"] == "put":
                    r = requests.put(url + msg["request"], data=data, headers=headers)
            else:
                r = requests.put(url + msg["request"], data=data, headers=headers)
            if r is not None:
                print(f"UE ({self.instance})", tsformat(datetime.now()), "<", r.status_code, r.reason)
            else:
                print (f"UE ({self.instance})", "< error")
                return(None)
            # jprint(json.loads(r.text))
            try:
                result.append(json.loads(r.text))
            except:
                pass # JSON error?
        return (r.status_code, result)


    def sendFromFile(self, msgfile, template=True, suppressBodyPrint = False):
        print(f"UE ({self.instance})","sendFromFile", msgfile)
        with open(msgfile) as json_file:
            msg = json.load(json_file)
        return self.sendMessage(msg, template=template, suppressBodyPrint=suppressBodyPrint)


    # TODO: Parse arbitrary key-value pairs and/or JSON
    def sendFromFileWithReplacement(self, msgfile, args, template=True, suppressBodyPrint = False):
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
        return self.sendMessage(msg, template=template, suppressBodyPrint=suppressBodyPrint)

    def checkConnection(self):
        print("---- Testing connectivity to UE")
        (sc, result) = self.sendFromFile(os.path.join(self.internalMessageRoot,"checkConnectivity.json"),template=False, suppressBodyPrint = True)
        # TODO: Check for timeouts
        if sc is not None and sc==200:
            print(f"UE ({self.instance}) connectivity OK")
        else:
            print(f"UE ({self.instance}) connectivity FAILED!", sc, result)
            return sc

        #check that the right map is loaded
        (sc, result) = self.sendFromFile(os.path.join(self.internalMessageRoot, "checkWorld.json"), template=True, suppressBodyPrint = True)

        if sc is not None and sc==200:
            print(f"UE ({self.instance}) world check OK:", result)
            return sc
        else:
            print(f"UE ({self.instance}) world check failed!", sc, result)
            return sc


        #jprint(result)
