import json
import boto3
import asyncio
class SQSNotifier:

    def __init__(self, sqs, sns, queue_url, bucket,  pipeline, module, start_phase, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.sqs = sqs
        self.sns = sns
        self.queue_url = queue_url
        self.bucket = bucket
        self.pipeline = pipeline
        self.message_attributes = {
            "module": {
                "DataType": "String",
                "StringValue": f"{module}"
            },
            "phase": {
                "DataType": "String",
                "StringValue": f"{start_phase}"
            }
        }

    #TODO: Not finished
    def monitor(self):
        return
        self.logger.debug("starting SQSNotifier.monitor")
        self.topic_arn = "arn:aws:sns:us-west-2:976618892613:dev-xanadu"
        queue = self.sqs.create_queue(
            QueueName=f"sns_queue_hermes_ch",
            Attributes={"ReceiveMessageWaitTimeSeconds": "20"}
        )
        self.logger.debug(f"queue {queue}")
        self.queue_url = queue["QueueUrl"]
        self.queue_arn = self.sqs.get_queue_attributes(
            QueueUrl=self.queue_url,
            AttributeNames=["QueueArn"]
        )["Attributes"]["QueueArn"]
        policy = {
            "Version": "2012-10-17",
            "Id": f"{self.queue_arn}/SQSDefaultPolicy",
            "Statement": [{
                "Sid": "Allow-SNS-SendMessage",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "SQS:SendMessage",
                "Resource": self.queue_arn,
                "Condition": {"ArnEquals": {"aws:SourceArn": self.topic_arn}}
            }]
        }
        self.sqs.set_queue_attributes(
            QueueUrl=self.queue_url,
            Attributes={"Policy": json.dumps(policy)}
        )
        self.sns.subscribe(
            TopicArn=self.topic_arn,
            Protocol="sqs",
            Endpoint=self.queue_arn
        )
        self.logger.debug("waiting...")
        while True:
            msgs = self.sqs.receive_message(
                QueueUrl=self.queue_url,
                WaitTimeSeconds=20,
                MaxNumberOfMessages=10
            )
            for msg in msgs.get("Messages", []):
                self.logger.info(json.loads(msg["Body"]))
                self.sqs.delete_message(
                    QueueUrl=self.queue_url,
                    ReceiptHandle=msg["ReceiptHandle"]
                )

    def notify(self, media_files, metadata_file):
        media_arns = {}
        for k,v in media_files.items():
            media_arns[k] = f"arn:aws:s3:::{self.bucket}/{v}"
        self.message_body = {
            "media_arns": media_arns, #f"arn:aws:s3:::{self.bucket}/{media_file}",
            "metadata_arn": f"arn:aws:s3:::{self.bucket}/{metadata_file}",
            "pipeline": f"{self.pipeline}"
        }
        self.logger.debug(self.queue_url)
        self.logger.debug(self.message_body)
        self.logger.debug(self.message_attributes)
        response = self.sqs.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(self.message_body),
            MessageAttributes=self.message_attributes
        )
        self.logger.debug(response)
        if response is None:
            self.logger.error("SQS Notifier response None")
        elif response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 200:
            self.logger.info(f"SQS Notifier successful: {response}")
        else:
            self.logger.error(f'SQS Notifier got rc: {response.get("ResponseMetadata", {}).get("HTTPStatusCode")} - {response}')
        return response