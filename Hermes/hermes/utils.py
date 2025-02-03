import json
def jprint(text):
    if isinstance(text,list):
        for t in text:
            print(json.dumps(t, indent=4))
    else:
        print(json.dumps(text, indent=4))
def jformat(text):
    if isinstance(text,list):
        for t in text:
            return(json.dumps(t, indent=4))
    else:
        return(json.dumps(text, indent=4))

def tsformat(ts):
    return ts.strftime("%Y-%m-%d %H:%M:%S.%f")
def setParam(json,field,value):
    json["body"]["parameters"][field] = value
def splitHostPort(s):
    host,port = s.split(":")
    return (host,int(port))
def splitInstanceHostPort(s):
    instance,host,port = s.split(":")
    return (instance,host,int(port))

## TODO: Check that works for sublevel - I think this is correct...
##
def reviseTemplateForPIE(newtpl):
    if "world" in newtpl:
        parts = newtpl["world"].rsplit("/", 1)
        parts[-1] = newtpl["_pie"] + parts[-1]
        newtpl["world"] = "/".join(parts)
    if "prefix" in newtpl:
        newtpl["prefix"] += newtpl["_pie"]


import logging

from colorama import just_fix_windows_console
just_fix_windows_console()
class ColorFormatter(logging.Formatter):
    # Define ANSI escape codes for colors
    COLORS = {
        logging.INFO: "\033[97m",    # Default (gray)
        logging.WARNING: "\033[93m",  # Yellow
        logging.ERROR: "\033[31m",    # Red
        logging.CRITICAL: "\033[1;31m",  # Bright Red
        logging.DEBUG: "\033[37m",    # Grey
    }
    RESET = "\033[0m"

    def format(self, record):
        # Get the color for the log level
        color = self.COLORS.get(record.levelno, self.RESET)
        message = super().format(record)
        # Apply color and reset formatting
        return f"{color}{message}{self.RESET}"

