from flask import Config
from base_mq import BaseMQ
from app_mq_rabbitmq import RabbitMQ
from app_mq_kafka import KafkaMQ
from app_mq_mongodb import MongoDBMQ  # ← NEW IMPORT

class AppMessageQueue:
    def __init__(self, logger, config: Config):
        self.config = config
        self.logger = logger
        self.vendor = config["MQ_VENDOR"]

    def open(self):
        if self.vendor == 'rabbitmq':
            return RabbitMQ(self.config)
        elif self.vendor == 'kafka':
            return KafkaMQ(self.config)
        elif self.vendor == 'mongodb':  # ← NEW CASE
            return MongoDBMQ(self.config)
        else:
            raise NotImplementedError(f"Unsupported MQ vendor: {self.vendor}")
