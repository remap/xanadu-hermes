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

print("\n --- \n")


import boto3
import json
import threading

queue_name = "temporary-queue"
sns_topic_arn = "arn:aws:sns:us-west-2:976618892613:dev-xanadu--ch1--raw-input--to--preprocess"

sqs = session.client("sqs")
sns = session.client("sns")

response = sqs.create_queue(QueueName=queue_name)
queue_url = response["QueueUrl"]

queue_attributes = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])
queue_arn = queue_attributes["Attributes"]["QueueArn"]

sns.subscribe(
    TopicArn=sns_topic_arn,
    Protocol="sqs",
    Endpoint=queue_arn,
)

policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "sns.amazonaws.com"},
            "Action": "sqs:SendMessage",
            "Resource": queue_arn,
            "Condition": {"ArnEquals": {"aws:SourceArn": sns_topic_arn}},
        }
    ],
}

sqs.set_queue_attributes(
    QueueUrl=queue_url,
    Attributes={"Policy": json.dumps(policy)},
)

def listen_to_sqs():
    try:
        while True:
            messages = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=10,
            )
            if "Messages" in messages:
                for message in messages["Messages"]:
                    print("Received message:", message["Body"])
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
msg = """
    {
      "media_arn": "arn:aws:s3:::dev-xanadu-raw-input/person.png",
      "metadata_arn": "arn:aws:s3:::dev-xanadu-raw-input/person.json"
    }
"""
response = client.publish(
    TopicArn = "arn:aws:sns:us-west-2:976618892613:dev-xanadu--ch1--raw-input--to--preprocess",
    Message = msg,
)
pprint.pp(response)
print("\n --- \n")
pprint.pp(glom(response, 'ResponseMetadata.HTTPStatusCode'))


# Wait
try:
    while True:
        pass
except KeyboardInterrupt:
    sqs.delete_queue(QueueUrl=queue_url)
    print("Queue deleted.")


