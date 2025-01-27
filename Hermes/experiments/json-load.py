
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