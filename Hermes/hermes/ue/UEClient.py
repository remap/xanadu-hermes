# Replace a specific parameter
# setParam(msg, "bNewVisibility", True if args.value.lower() in ('true') else False)
import json
import requests
import os
from datetime import datetime, timedelta
from hermes.utils import tsformat, jformat
import logging
from hermes.template import Template
import re
from glom import glom
UE5_DEFAULT_TIMEOUT = 1   # TODO: Arg / slower?
MAX_WORKERS = 5
import concurrent.futures

class UEClient:

    def __init__(self, ueurl, instance=None, prefix=None, template=None, internalMessageRoot=None, paramRoot=None, connectivityCheck=False, mapNames=False, isPIE=False, name=""):
        self.ueurl = ueurl
        self.instance = instance  # Firebase namespace
        self.prefix = prefix # legacy prefix templater
        self.template = template
        self.actorTemplate = None
        self.internalMessageRoot = internalMessageRoot
        self.paramRoot = paramRoot
        self.connectivityCheck = connectivityCheck
        self.mapNames = mapNames
        self.name = name
        #self.asyncRequests = True  #not exposed
        self.isPIE = isPIE
        self.logger = logging.getLogger(f"{self.__class__.__name__} {self.instance}")
        self.logger.setLevel(logging.DEBUG)

        #if self.asyncRequests:
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

    def __del__(self):
        self.executor.shutdown(wait=False)  # TODO: ??

    def setActorTemplate(self, t):
        self.actorTemplate=t

    def replace_placeholders(self, source_dict, replacement_dict):
        """
        Recursively scans and replaces placeholders of the form {{_.path.to.value}} in a dictionary
        with values from the replacement dictionary.

        Supports whitespace variations and ensures paths start with '_.'
        while leveraging glom syntax for path matching.

        :param source_dict: The dictionary containing placeholders.
        :param replacement_dict: The dictionary used for replacement values.
        :return: A new dictionary with placeholders replaced.
        """
        p = re.compile(r"\{\{\s*_\.(.+?)\s*\}\}")

        def replace_value(value):
            if isinstance(value, str):
                match = p.fullmatch(value)
                if match:
                    path = match.group(1).strip()
                    try:
                        return glom(replacement_dict, path)
                    except Exception as e:
                        raise ValueError(f"Error accessing path '{path}': {e}")
                return value
            elif isinstance(value, dict):
                return {k: replace_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [replace_value(item) for item in value]
            return value

        return replace_value(source_dict)


    def sendMessage(self, **kwargs):
        if "block" not in kwargs:
            return self._sendMessage(**kwargs)
        elif kwargs["block"]:
            del kwargs["block"]
            return self._sendMessage(**kwargs)
        else:
            del kwargs["block"]
            future = self.executor.submit(self._sendMessage, **kwargs)
            if not "callback" in kwargs:
                future.add_done_callback(lambda f : self.logger.info(f"Async return {f.result()[0]}")) # get rc
            else:
                future.add_done_callback(kwargs["callback"])  # future.result() is (rc, result)

    ###  Blocking http message
    ###  Goes through each message in the array in order
    #
    def _sendMessage(self, msgs=None, applyTemplates=False, suppressBodyPrint=False, templates=None,
                     timeout=UE5_DEFAULT_TIMEOUT, filepath=None, **kwargs):
        url = self.ueurl
        result = []
        if not isinstance(msgs, list):
            msgs = [msgs]

        for msg in msgs:

            # TODO: Should send return codes back
            self.logger.info(f"> {url} {msg['request']}")
            if "body" in msg:
                headers = {'Content-Type': 'application/json'}

                hasExternalParams = "externalParams" in msg


                if applyTemplates:

                    # TODO Optimize - limit the number of message searches?
                    # Legacy
                    if "objectPath" in msg["body"]: msg["body"]["objectPath"] = msg["body"]["objectPath"].replace(
                        "{{prefix}}", self.prefix)

                    ## ARGUMENTS IN OSC CALL
                    ##
                    # First, apply dynamic variables, which may refer to class variables.
                    if templates is not None:
                        for template in templates:
                            msg = template.replace_in_dict(msg)

                    ## TEMPLATE FILE
                    ##
                    # Then, apply the template file, which may be referred to from those variables
                    msg = self.template.replace_in_dict(msg)

                    ## EXTERNAL PARAMETERS JSON / FILE
                    ##
                    # Do here to allow file to be set via template
                    if "externalParamFile" in msg:
                        # Maybe do in send from File???   #
                        filename = os.path.join(filepath, msg["externalParamFile"])
                        self.logger.info(f"Loading external parameters {filename}")
                        if os.path.isfile(filename):
                            with open(filename) as json_file:
                                externalParams = json.load(json_file)
                            msg["externalParams"] = externalParams if "externalParams" not in msg else externalParams | msg["externalParams"]
                        else:
                            self.logger.warning(f"Could not load external parameter file {filename}")
                        # self.logger.debug(jformat(externalParams))

                    if "externalParams" in msg: hasExternalParams = True

                    # Apply the external parameters, if available
                    if hasExternalParams:
                        msg["body"] = self.replace_placeholders(msg["body"], msg["externalParams"])

                    ## REAPPLY TEMPLATE FILE
                    ##
                    # TODO: Do we need to do it again?
                    # Then, reapply dynamic vars, in case there are pointers in other direction
                    if templates is not None:
                        for template in templates:
                            msg = template.replace_in_dict(msg)

                    ## ACTOR NAME MAPPING (last)
                    ##
                    # Finally, apply actor name mapping:
                    if self.actorTemplate is not None:
                        msg = self.actorTemplate.replace_in_dict(msg)

                if not suppressBodyPrint: self.logger.debug(jformat(msg["body"]))
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
                self.logger.error (f"*** UE5 TIMEOUT")
                return (-1, None)

            if r is not None:
                if r.status_code == 200:
                    self.logger.info(f"< {r.status_code} {r.reason}")
                else:
                    self.logger.error(f"< {r.status_code} {r.reason}")
            else:
                self.logger.warning(f"< error")
                continue
            # jprint(json.loads(r.text))

            if r.status_code == 200 and r.text == "":
                return (r.status_code, None)
            try:

                text = json.loads(r.text)
                result.append(text)
                if not suppressBodyPrint:
                    if r.status_code == 200:
                        self.logger.info(jformat(text))
                    else:
                        self.logger.error(jformat(text))
            except:
                self.logger.warning(f"JSON parsing error with output {r.text}")
                pass  # JSON error?

        # TODO: isn't this just the last code if there are multiple?
        return (r.status_code, result)


    def sendFromFile(self, msgfile, **kwargs): #applyTemplates=True, suppressBodyPrint = False, templates=None, timeout=UE5_DEFAULT_TIMEOUT, params=None, block=False):
        self.logger.info(f"sendFromFile {msgfile}")
        with open(msgfile) as json_file:
            msg = json.load(json_file)

        if "params" in kwargs and kwargs["params"] is not None:  #call_generic support
            msg["body"]["parameters"]=kwargs["params"]
        #TODO try/catch

        kwargs["filepath"]=self.paramRoot #os.path.dirname(msgfile)
        if "block" not in kwargs: kwargs["block"] = False # ToDo async by default?
        return self.sendMessage(msgs=msg, **kwargs) #applyTemplates=applyTemplates, suppressBodyPrint=suppressBodyPrint, templates=templates, timeout=timeout, filepath=os.path.dirname(msgfile), block = block)

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

    def checkConnection(self, force=False):
        if self.connectivityCheck==False and not force:
            self.logger.warning(f"---- Skipping connectivity check to UE for {self.instance}")
            return
        self.logger.info(f"---- Testing connectivity to UE for {self.instance}")
        (sc, result) = self.sendFromFile(os.path.join(self.internalMessageRoot,"checkConnectivity.json"),
                                         applyTemplates=False, suppressBodyPrint = True, timeout=1, block=True)
        # TODO: Check for timeouts
        if sc is not None and sc==200:
            self.logger.info(f"connectivity OK")
        else:
            self.logger.error(f"connectivity FAILED! {sc} {result}")
            return sc

        #check that the right map is loaded
        (sc, result) = self.sendFromFile(os.path.join(self.internalMessageRoot, "checkWorld.json"),
                                         applyTemplates=True, suppressBodyPrint = True, timeout=1, block=True)

        if sc is not None and sc==200:
            self.logger.info(f"world check OK: {str(result)[:150]}...")
            return sc
        else:
            self.logger.error(f"world check failed! {sc} {result}")
            return sc

    def getNameMap(self, dump=False, force=False, useGlobal=False):
        if self.mapNames==False and not force:
            self.logger.warning(f"---- Skipping name map load {self.instance}")
            return
        self.logger.info(f"----  Name map load to UE for {self.instance}")
        if useGlobal:
            self.sendFromFile(os.path.join(self.internalMessageRoot, "dumpGlobalNameMap.json"),
                                            suppressBodyPrint=True, applyTemplates=True, block=False,
                                            callback=lambda future : self.processNameMap(future.result()[1],dump))
        else:
            self.sendFromFile(os.path.join(self.internalMessageRoot, "dumpActorNameMap.json"),
                                            suppressBodyPrint=True, applyTemplates=True, block=False,
                                            callback=lambda future : self.processNameMap(future.result()[1],dump))
        #self.processNameMap(result, dump)
        return

    ## Set our name map (called async by getNameMap)
    #
    def processNameMap(self, result, dump):
        if result is None:
            #self.logger.error(f"processNameMap got None as input")
            return
            # try:

        if len(result) == 0:
            self.logger.error(f"processNameMap got zero-length result as input")
            return

        if not isinstance(result,list):
            self.logger.error(f"processNameMap got non-list result as input: {result}")
            return

            # try:
        if "ReturnValue" not in result[0]:
            self.logger.error(f"processNameMap no ReturnValue key:  {result}")
            return

        map = json.loads(result[0]["ReturnValue"])#
        if self.isPIE and "_pie" in self.template:
            for k in map:
                if not self.template["_pie"] in map[k]: # /Memory objects already have PIE prefix
                    comps = map[k].split("/")
                    comps[-1] = self.template["_pie"]+comps[-1]
                    map[k] = "/".join(comps)
                   #print(map[k])
                    #map[k] = map[k].replace(self.template["_prefix"], self.template["_prefix"]+self.template["pie"])

        if dump: self.logger.debug(jformat(map))
        self.logger.info(f"Loaded {len(map)} name maps.")
        self.setActorTemplate(Template(map))
    # except:  # TODO: Fix exception detail
    #     self.logger.error("Exception in loading map")

        #jprint(result)
