class SQSNotifier:

    def __init__(self, sqs, queue_url, bucket,  pipeline, module, start_phase, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.sqs = sqs
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

    def notify(self, media_file, metadata_file):
        self.message_body = {
            "media_arn": f"arn:aws:s3:::{self.bucket}/{media_file}",
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