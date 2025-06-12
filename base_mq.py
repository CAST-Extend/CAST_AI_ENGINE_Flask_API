# base_mq.py

class BaseMQ:
    def close(self):
        raise NotImplementedError()

    def publish(self, topic, message):
        raise NotImplementedError()

    def process(self, topic, callback):
        raise NotImplementedError()

    def get(self, topic):
        raise NotImplementedError()
