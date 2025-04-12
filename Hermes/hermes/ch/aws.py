import json
import boto3
import asyncio



class SQSListener:
    def __init__(self, sqs, sns, listen_queue_name, listen_topic_arn, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.sqs = sqs
        self.sns = sns
        self.listen_queue_name = listen_queue_name
        self.listen_topic_arn = listen_topic_arn
        self.listen_callbacks = {}
        # listen_queue, used for SNS subscriptions
        # Use one specific to our instance, create if needed
        #
        try:
            response = sqs.get_queue_url(QueueName=self.listen_queue_name)
            self.listen_queue_url = response["QueueUrl"]
            self.logger.info(f"SQS Listen Queue: URL: {self.listen_queue_url}")
        except sqs.exceptions.QueueDoesNotExist:
            # Create the listen_queue if needed
            response = sqs.create_queue(QueueName=self.listen_queue_name)
            self.listen_queue_url = response["QueueUrl"]
            self.logger.warning(f"SQS Listen Queue does not exist, created: {self.listen_queue_url}")
            attributes = sqs.get_queue_attributes(
                QueueUrl=self.listen_queue_url,
                AttributeNames=['QueueArn']
            )
            self.listen_queue_arn = attributes['Attributes']['QueueArn']
            self.listen_subscribe_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "sns.amazonaws.com"},
                        "Action": "sqs:SendMessage",
                        "Resource": self.listen_queue_arn,
                        "Condition": {"ArnEquals": {"aws:SourceArn": self.listen_topic_arn}},
                    }
                ],
            }
            try:
                sqs.set_queue_attributes(
                    QueueUrl=self.listen_queue_url,
                    Attributes={"Policy": json.dumps(self.listen_subscribe_policy)},
                )
            except Exception as error:
                self.logger.error("SQS Listen Error setting queue policy:", error, exc_info=True)
                self.listen_queue_arn = None
        except Exception as error:
            self.logger.error("SQS Listen An error occurred:", error)
            self.listen_queue_url = None

        # Purge the queue
        try:
            response = self.sqs.purge_queue(QueueUrl=self.listen_queue_url)
            self.logger.debug("Queue purged successfully.")
        except Exception as error:
            # This will catch errors like if you try to purge within 60 seconds of a previous purge
            self.logger.error(f"Error purging queue {self.listen_queue_url}: %s", error)

        # Get the corresponding ARN
        try:
            self.listen_queue_arn = self.sqs.get_queue_attributes(
                QueueUrl=self.listen_queue_url,
                AttributeNames=["QueueArn"]
            )["Attributes"]["QueueArn"]
        except Exception as error:
            self.logger.error("SQS Listen Error getting listen queue arn: %s", error)
            self.listen_queue_arn = None

    def add_callback(self, key, listen_callback):
        self.listen_callbacks[key] = listen_callback

    def remove_callback(self, key):
        if key in self.listen_callbacks:
            del self.listen_callbacks[key]

    def monitor(self):

        self.logger.debug("starting SQSListener.monitor")

        try:
            self.sns.subscribe(
                TopicArn=self.listen_topic_arn,
                Protocol="sqs",
                Endpoint=self.listen_queue_arn,
            )
            self.logger.info(f"Subscribed {self.listen_queue_arn} to {self.listen_topic_arn}")
        except Exception as e:
            self.logger.error(f"SQS Listen exception subscribing {self.listen_queue_arn} to {self.listen_topic_arn}", exc_info=True)


        #self.logger.debug("waiting...")
        while True:
            #self.logger.debug("Waiting for SQS...")
            try:
                msgs = self.sqs.receive_message(
                    QueueUrl=self.listen_queue_url,
                    WaitTimeSeconds=5,
                    MaxNumberOfMessages=10
                )
                for msg in msgs.get("Messages", []):
                    payload =  json.loads(msg["Body"])["Message"]
                    jpayload = None
                    try:
                        jpayload = json.loads(payload)
                        module = jpayload.get("module", "[no module]")
                        self.logger.debug(f"SQS Listen Received {module} message: {payload}")
                    except:
                        self.logger.error(f"SQS Listen Received unparseable message: {payload}")
                        return
                    try:
                        #self.listen_callback(payload)
                        for key, callback in self.listen_callbacks.items():
                            try:
                                callback(jpayload)
                            except Exception as e:
                                self.logger.error(f"Exception in SQS Listen listen_callback with key {key}: {e}", exc_info=True)
                    except Exception as e:
                        self.logger.error("Exception in SQS Listen listen_callback", exc_info=True )
                    self.sqs.delete_message(
                        QueueUrl=self.listen_queue_url,
                        ReceiptHandle=msg["ReceiptHandle"]
                    )
            except Exception as e:
                self.logger.error("Error in SQS Listen monitor loop", exc_info=True)


class SQSNotifier:

    def __init__(self, sqs, sns, notify_queue_name, bucket,  pipeline, module, start_phase, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.sqs = sqs
        self.sns = sns
        self.notify_queue_name = notify_queue_name
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

        # notify_queue, used to tell lambda to process
        # Only one, get it.
        try:
            response = sqs.get_queue_url(QueueName=self.notify_queue_name)
            self.notify_queue_url = response["QueueUrl"]
            self.logger.info(f"SQS Notify Queue: URL: {self.notify_queue_url}")
        except Exception as error:
            self.logger.error("SQS Notify Error getting notify queue url:", error)
            self.notify_queue_url = None

    def notify(self, media_files, metadata_file):
        media_arns = {}
        for k,v in media_files.items():
            media_arns[k] = f"arn:aws:s3:::{self.bucket}/{v}"
        self.message_body = {
            "media_arns": media_arns, #f"arn:aws:s3:::{self.bucket}/{media_file}",
            "metadata_arn": f"arn:aws:s3:::{self.bucket}/{metadata_file}",
            "pipeline": f"{self.pipeline}"
        }
        self.logger.debug(f"SQS notify QueueURL: {self.notify_queue_url}")
        self.logger.debug(f"SQS notify MessageBody: {self.message_body}")
        self.logger.debug(f"SQS notify MessageAttributes: {self.message_attributes}")
        response = self.sqs.send_message(
            QueueUrl=self.notify_queue_url,
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