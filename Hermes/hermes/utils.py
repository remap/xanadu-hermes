import json
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
def splitInstanceHostPort(s):
    instance,host,port = s.split(":")
    return (instance,host,int(port))