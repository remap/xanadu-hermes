# Replace a specific parameter
# setParam(msg, "bNewVisibility", True if args.value.lower() in ('true') else False)
import json
import requests
import os
from datetime import datetime, timedelta
from hermes.utils import tsformat, jprint

UE5_DEFAULT_TIMEOUT = 1   # TODO: Arg / slower?

class UEClient:

    def __init__(self, ueurl, instance=None, prefix=None, template=None, internalMessageRoot=None, connectivityCheck=False, name=""):
        self.ueurl = ueurl
        self.instance = instance  # Firebase namespace
        self.prefix = prefix # legacy prefix templater
        self.template = template
        self.internalMessageRoot = internalMessageRoot
        self.connectivityCheck = connectivityCheck
        self.name = name


    def sendMessage(self, msgs, applyTemplates=False, suppressBodyPrint = False, templates=None, timeout=UE5_DEFAULT_TIMEOUT):
        url = self.ueurl
        result = []
        if not isinstance(msgs, list):
            msgs = [msgs]

        for msg in msgs:
            # TODO: Should send return codes back
            print(f"UE ({self.instance})", tsformat(datetime.now()), ">", url + msg["request"])
            if "body" in msg:
                headers = {'Content-Type': 'application/json'}
                if applyTemplates:

                    # TODO Optimize - limit the number of message searches?
                    # Legacy
                    if "objectPath" in msg["body"]: msg["body"]["objectPath"] = msg["body"]["objectPath"].replace(
                        "{{prefix}}", self.prefix)
                    # Class template
                    msg = self.template.replace_in_dict(msg)
                    # Additional templates
                    if templates is not None:
                        for template in templates:
                            msg = template.replace_in_dict(msg)
                if not suppressBodyPrint: jprint(msg["body"])
                data = json.dumps(msg["body"])
            else:
                headers = None
                data = None
            r=None
            try:
                if "method" in msg:
                    if msg["method"] == "get":
                        r = requests.get(url + msg["request"], data=data, headers=headers, timeout=timeout)
                    if msg["method"] == "put":
                        r = requests.put(url + msg["request"], data=data, headers=headers, timeout=timeout)
                else:
                    r = requests.put(url + msg["request"], data=data, headers=headers, timeout=timeout)
            except requests.exceptions.Timeout:
                print (f"*** UE5 TIMEOUT: {self.instance}")
                return (-1, None)
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


    def sendFromFile(self, msgfile, applyTemplates=True, suppressBodyPrint = False, templates=None, timeout=UE5_DEFAULT_TIMEOUT):
        print(f"UE ({self.instance})","sendFromFile", msgfile)
        with open(msgfile) as json_file:
            msg = json.load(json_file)
        return self.sendMessage(msg, applyTemplates=applyTemplates, suppressBodyPrint=suppressBodyPrint, templates=templates, timeout=timeout)

    #
    # # TODO: Parse arbitrary key-value pairs and/or JSON
    # def sendFromFileWithReplacement(self, msgfile, args, template=True, suppressBodyPrint = False):
    #     print("sendFromFileWithReplacement", msgfile)
    #     # Need casting?  Quick boolean fix
    #     if args[3].lower() == 'true':
    #         v = True
    #     elif args[3].lower() == 'false':
    #         v = False
    #     else:
    #         v = args[3]
    #     with open(msgfile) as json_file:
    #         msg = json.load(json_file)
    #
    #     setParam(msg, args[2], v)
    #     # print(msg)
    #     return self.sendMessage(msg, template=template, suppressBodyPrint=suppressBodyPrint)

    def checkConnection(self):
        if self.connectivityCheck==False:
            print(f"---- Skipping connectivity check to UE for {self.instance}")
            return
        print(f"---- Testing connectivity to UE for {self.instance}")
        (sc, result) = self.sendFromFile(os.path.join(self.internalMessageRoot,"checkConnectivity.json"),applyTemplates=False, suppressBodyPrint = True, timeout=1)
        # TODO: Check for timeouts
        if sc is not None and sc==200:
            print(f"UE ({self.instance}) connectivity OK")
        else:
            print(f"UE ({self.instance}) connectivity FAILED!", sc, result)
            return sc

        #check that the right map is loaded
        (sc, result) = self.sendFromFile(os.path.join(self.internalMessageRoot, "checkWorld.json"), applyTemplates=True, suppressBodyPrint = True, timeout=1)

        if sc is not None and sc==200:
            print(f"UE ({self.instance}) world check OK:", result)
            return sc
        else:
            print(f"UE ({self.instance}) world check failed!", sc, result)
            return sc


        #jprint(result)
