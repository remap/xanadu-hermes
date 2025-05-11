import boto3
import json
import types
import pprint
from glom import glom

with open("../xanadu-secret-aws.json") as f:
    config = types.SimpleNamespace(**json.load(f))
print(config)
session = boto3.Session(
    aws_access_key_id=config.access_key,
    aws_secret_access_key=config.secret_key,
    region_name=config.region_name
)

# client = session.client('s3')
# response = client.list_buckets()
#
# pprint.pp(response)
# print("\n --- \n")
# pprint.pp(glom(response, 'Buckets.*.Name'))
#
# print("\n --- \n")


import boto3
import json
import threading
import uuid
import sys
import time
from datetime import datetime

environ = "dev"
instance = "jb_testing"
queue_name = f"{environ}-xanadu-hermes-ch-{instance}"
print(queue_name)
queue_url = "https://sqs.us-west-2.amazonaws.com/976618892613/" + queue_name
sns_topic_arn = f"arn:aws:sns:us-west-2:976618892613:{environ}-xanadu"   # TODO: instance?

sqs = session.client("sqs")
sns = session.client("sns")

try:
    response = sqs.get_queue_url(QueueName=queue_name)
    print("Queue exists. URL:", response['QueueUrl'])
    queue_url = response["QueueUrl"]
except sqs.exceptions.QueueDoesNotExist:
    print("Queue does not exist, creating.")
    response = sqs.create_queue(QueueName=queue_name)
    queue_url = response["QueueUrl"]
except Exception as error:
    print("An error occurred:", error)
    queue_url = None

queue_attributes = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])
queue_arn = queue_attributes["Attributes"]["QueueArn"]

print(queue_url)
print(queue_arn)
try:
    sns.subscribe(
        TopicArn=sns_topic_arn,
        Protocol="sqs",
        Endpoint=queue_arn,
    )
    print(f"Subscribed {queue_arn} to {sns_topic_arn}")
except Exception as e:
    print("exception subscribing")
#
# policy = {
#     "Version": "2012-10-17",
#     "Statement": [
#         {
#             "Effect": "Allow",
#             "Principal": {"Service": "sns.amazonaws.com"},
#             "Action": "sqs:SendMessage",
#             "Resource": queue_arn,
#             "Condition": {"ArnEquals": {"aws:SourceArn": sns_topic_arn}},
#         }
#     ],
# }
# sqs.set_queue_attributes(
#     QueueUrl=queue_url,
#     Attributes={"Policy": json.dumps(policy)},
# )

def listen_to_sqs():
    try:
        while True:
            #print("loop")
            messages = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=10,
            )
            if "Messages" in messages:
                for message in messages["Messages"]:
                    print("Received message:", json.loads(message["Body"])["Message"])
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=message["ReceiptHandle"],
                    )
    except KeyboardInterrupt:
        print("Stopped listening.")

listener_thread = threading.Thread(target=listen_to_sqs, daemon=True)
listener_thread.start()
print("Listener started. Press Ctrl+C to stop.")


client = session.client('sns')
msg = f"""
    {{
      "media_arn": "arn:aws:s3:::dev-xanadu-raw-input/person.png",
      "metadata_arn": "arn:aws:s3:::dev-xanadu-raw-input/person.json",
      "time": {datetime.now()}
    }}
"""
response = client.publish(
    TopicArn = sns_topic_arn,
    Message = msg,
)
time.sleep(2)
print("Publishing a test message", msg)
#pprint.pp(response)
#print("\n --- \n")
pprint.pp(glom(response, 'ResponseMetadata.HTTPStatusCode'))


# Wait
try:
    while True:
        pass
except KeyboardInterrupt:
    pass
    # sqs.delete_queue(QueueUrl=queue_url)
    # print("Queue deleted.")


