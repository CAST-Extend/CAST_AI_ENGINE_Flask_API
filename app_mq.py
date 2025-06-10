from flask import Config
from app_mq_rabbitmq import RabbitMQ
from app_mq_kafka import KafkaMQ
from app_mq_mongodb import MongoDBMQ

class AppMessageQueue:
    def __init__(self, logger, config: Config):
        self.config = config
        self.logger = logger
        self.vendor = config["MQ_VENDOR"]

    async def open(self):
        if self.vendor == 'rabbitmq':
            raise NotImplementedError("RabbitMQ is not async-supported in current setup.")
        elif self.vendor == 'kafka':
            raise NotImplementedError("Kafka is not async-supported in current setup.")
        elif self.vendor == 'mongodb':
            return MongoDBMQ(self.config)
        else:
            raise NotImplementedError(f"Unsupported MQ vendor: {self.vendor}")
