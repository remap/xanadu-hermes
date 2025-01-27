from firebase_functions import https_fn, db_fn
from firebase_admin import initialize_app
# borrowed logging from: https://github.com/firebase/firebase-functions-python/blob/f51659435461ff6c9ccd77e14132e428262f4a2b/src/firebase_functions/tasks_fn.py#L29 
from functions_framework import logging as _logging

import boto3  #aws

import json
from pprint import pformat
import types
from glom import glom   # json access
from datetime import datetime 
instance = "xanadu"

initialize_app()
 

with open("xanadu-secret-aws.json") as f:
    config = types.SimpleNamespace(**json.load(f))

session = boto3.Session(
    aws_access_key_id=config.access_key,
    aws_secret_access_key=config.secret_key,
    region_name=config.region_name
)


client = session.client('sns')
msg = { 
      "created" : datetime.now().strftime("%m-%d-%Y %H:%M:%S"),
      "source"  : "hermes-fb", 
      "trigger" : {}, 
      "media_arn": "arn:aws:s3:::dev-xanadu-raw-input/person.png",
      "metadata_arn": "arn:aws:s3:::dev-xanadu-raw-input/person.json"
      }
topic = "arn:aws:sns:us-west-2:976618892613:dev-xanadu--ch1--raw-input--to--preprocess"

     
# for more on firebase function sin python, see the repo: 
# https://github.com/firebase/firebase-functions-python?tab=readme-ov-file
    
@db_fn.on_value_created(reference=f"{instance}/hello")
def proc_created(event: db_fn.Event):
	print("created:\n",pformat(event))	

@db_fn.on_value_deleted(reference=f"{instance}/hello")
def proc_deleted( event: db_fn.Event):
	print("deleted:\n",pformat(event))	

@db_fn.on_value_updated(reference=f"{instance}/hello")
def proc_update( event: db_fn.Event): 
	print("updated:\n",pformat(event))	
	
@db_fn.on_value_written(reference=f"{instance}/hello")
def proc_written(event: db_fn.Event): 
	print("written:\n",pformat(event))	
	try:
		msg["trigger"]["key"] = event.reference
		msg["trigger"]["value"] = event.data.after
		print("sns publish message:\n", pformat(msg)) 
		response = client.publish(TopicArn = topic, Message = json.dumps(msg))
		print("sns publish response:\n", pformat(response))
		print(f"sns publish rc: {glom(response, 'ResponseMetadata.HTTPStatusCode')}")
	except Exception as e:
		print("exception in publishing sns message:", repr(e))


# https handler
# @https_fn.on_request()
# def on_request(req: https_fn.Request) -> https_fn.Response:
#      return https_fn.Response("Hello world!")