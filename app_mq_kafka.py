# from kafka import KafkaProducer, KafkaConsumer
# from flask import Config as FlaskConfig
# import json, threading

# class KafkaMQ(BaseMQ):
#     def __init__(self, config: FlaskConfig):
#         self.config = config
#         self._lock = threading.Lock()
#         self.producer = KafkaProducer(
#             bootstrap_servers=config["KAFKA_BOOTSTRAP_SERVERS"],
#             value_serializer=lambda v: json.dumps(v).encode("utf-8")
#         )
#         self.consumers = []

#     def close(self):
#         with self._lock:
#             self.producer.close()
#         for consumer in self.consumers:
#             consumer.close()

#     def publish(self, topic, message):
#         with self._lock:
#             self.producer.send(topic, message)
#             self.producer.flush()

#     def process(self, topic, callback):
#         def run():
#             consumer = KafkaConsumer(
#                 topic,
#                 bootstrap_servers=self.config["KAFKA_BOOTSTRAP_SERVERS"],
#                 group_id=self.config["KAFKA_GROUP_ID"],
#                 enable_auto_commit=True,
#                 session_timeout_ms=10000,
#                 heartbeat_interval_ms=3000,
#                 max_poll_interval_ms=300000,
#                 auto_offset_reset=self.config["KAFKA_AUTO_OFFSET_RESET"],
#                 value_deserializer=lambda m: json.loads(m.decode("utf-8"))
#             )
#             self.consumers.append(consumer)
#             for msg in consumer:
#                 callback(msg.value)

#         thread = threading.Thread(target=run, daemon=True)
#         thread.start()

#     def get(self, topic):
#         consumer = KafkaConsumer(
#             topic,
#             bootstrap_servers=self.config["KAFKA_BOOTSTRAP_SERVERS"],
#             group_id=None,
#             auto_offset_reset=self.config["KAFKA_AUTO_OFFSET_RESET"],
#             consumer_timeout_ms=1000,
#             value_deserializer=lambda m: json.loads(m.decode("utf-8"))
#         )
#         for msg in consumer:
#             return msg.value
#         return None