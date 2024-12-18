import boto3
import json
import types
import pprint
from glom import glom

with open("xanadu-secret-aws.json") as f:
    config = types.SimpleNamespace(**json.load(f))
print(config)
session = boto3.Session(
    aws_access_key_id=config.access_key,
    aws_secret_access_key=config.secret_key,
    region_name=config.region_name
)
client = session.client('s3')
response = client.list_buckets()

pprint.pp(response)
print("\n --- \n")
pprint.pp(glom(response, 'Buckets.*.Name'))
