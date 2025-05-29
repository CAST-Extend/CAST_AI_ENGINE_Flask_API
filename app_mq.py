from flask import Config as FlaskConfig
from app_mq_rabbitmq import RabbitMQ
from app_mq_kafka import KafkaMQ

class AppMessageQueue:
    def __init__(self, logger, config: FlaskConfig):
        self.config = config
        self.logger = logger
        self.vendor = config["MQ_VENDOR"]

    def open(self):
        if self.vendor == 'rabbitmq':
            return RabbitMQ(self.config)
        elif self.vendor == 'kafka':
            return KafkaMQ(self.config)
        else:
            raise NotImplementedError(f"Unsupported MQ vendor: {self.vendor}")

# message queue interface
class BaseMQ:
    def close(self):
        raise NotImplementedError()

    def publish(self, topic, message):
        raise NotImplementedError()

    def process(self, topic, callback):
        raise NotImplementedError()

    def get(self, topic):
        raise NotImplementedError()
