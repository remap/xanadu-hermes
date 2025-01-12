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


class UEClient:

    def __init__(self, ueurl, instance=None, prefix=None, template=None, internalMessageRoot=None, connectivityCheck=False, mapNames=False, isPIE=False, name=""):
        self.ueurl = ueurl
        self.instance = instance  # Firebase namespace
        self.prefix = prefix # legacy prefix templater
        self.template = template
        self.actorTemplate = None
        self.internalMessageRoot = internalMessageRoot
        self.connectivityCheck = connectivityCheck
        self.mapNames = mapNames
        self.name = name
        self.isPIE = isPIE
        self.logger = logging.getLogger(f"{self.__class__.__name__} {self.instance}")
        self.logger.setLevel(logging.DEBUG)

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


    def sendMessage(self, msgs, applyTemplates=False, suppressBodyPrint = False, templates=None, timeout=UE5_DEFAULT_TIMEOUT):
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

                    # First, apply dynamic variables, which may refer to class variables.
                    if templates is not None:
                        for template in templates:
                            msg = template.replace_in_dict(msg)

                    # Then, apply the template file, which may be referred to from those variables
                    msg = self.template.replace_in_dict(msg)

                    # Apply the external parameters, if available
                    if hasExternalParams:
                        msg["body"] = self.replace_placeholders(msg["body"], msg["externalParams"])


                    # TODO: Do we need to do it again?
                    # Then, reapply dynamic vars, in case there are pointers in other direction
                    if templates is not None:
                        for template in templates:
                            msg = template.replace_in_dict(msg)

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
                if r.status_code==200:
                    self.logger.info(f"< {r.status_code} {r.reason}")
                else:
                    self.logger.error(f"< {r.status_code} {r.reason}")
            else:
                self.logger.warning (f"< error")
                return(None)
            # jprint(json.loads(r.text))
            try:
                text = json.loads(r.text)
                result.append(text)
                if not suppressBodyPrint:
                    if r.status_code == 200:
                        self.logger.info(jformat(text))
                    else:
                        self.logger.error(jformat(text))
            except:
                self.logger.error(f"JSON parsing error with output {r.text}")
                pass # JSON error?
        return (r.status_code, result)


    def sendFromFile(self, msgfile, applyTemplates=True, suppressBodyPrint = False, templates=None, timeout=UE5_DEFAULT_TIMEOUT, params=None):
        self.logger.info(f"sendFromFile {msgfile}")
        with open(msgfile) as json_file:
            msg = json.load(json_file)

        if params is not None:  #call_generic support
            msg["body"]["parameters"]=params
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

    def checkConnection(self, force=False):
        if self.connectivityCheck==False and not force:
            self.logger.warning(f"---- Skipping connectivity check to UE for {self.instance}")
            return
        self.logger.info(f"---- Testing connectivity to UE for {self.instance}")
        (sc, result) = self.sendFromFile(os.path.join(self.internalMessageRoot,"checkConnectivity.json"),applyTemplates=False, suppressBodyPrint = True, timeout=1)
        # TODO: Check for timeouts
        if sc is not None and sc==200:
            self.logger.info(f"connectivity OK")
        else:
            self.logger.error(f"connectivity FAILED! {sc} {result}")
            return sc

        #check that the right map is loaded
        (sc, result) = self.sendFromFile(os.path.join(self.internalMessageRoot, "checkWorld.json"), applyTemplates=True, suppressBodyPrint = True, timeout=1)

        if sc is not None and sc==200:
            self.logger.info(f"world check OK: {result}")
            return sc
        else:
            self.logger.error(f"world check failed! {sc} {result}")
            return sc

    def getNameMap(self, dump=False, force=False):
        if self.mapNames==False and not force:
            self.logger.warning(f"---- Skipping name map load {self.instance}")
            return
        self.logger.info(f"----  Name map load to UE for {self.instance}")
        (rc, result) = self.sendFromFile(os.path.join(self.internalMessageRoot, "dumpActorNameMap.json"),
                                        suppressBodyPrint=True, applyTemplates=True)
        if result is not None:
            # try:
                map = json.loads(result[0]["ReturnValue"])#

                if self.isPIE and "prefix" in self.template and "pie" in self.template:
                    for k in map:
                        map[k] = map[k].replace(self.template["_prefix"], self.template["_prefix"]+self.template["pie"])

                if dump: self.logger.debug(jformat(map))
                self.logger.info(f"Loaded {len(map)} name maps.")
                self.setActorTemplate(Template(map))
            # except:  # TODO: Fix exception detail
            #     self.logger.error("Exception in loading map")

        return (rc,result)
        #jprint(result)
