import pika, json, threading
from flask import Config as FlaskConfig

class RabbitMQ:
    def __init__(self, config: FlaskConfig):
        self.config = config
        self.connection_params = pika.ConnectionParameters(
            host=config["RABBITMQ_HOST"],
            port=config["RABBITMQ_PORT"],
            virtual_host=config["RABBITMQ_VHOST"],
            credentials=pika.PlainCredentials(
                config["RABBITMQ_USER"], config["RABBITMQ_PASSWORD"]
            ),
            heartbeat=600,
            blocked_connection_timeout=300
        )
        self.thread_local = threading.local()

    def _get_channel(self):
        if not hasattr(self.thread_local, "connection"):
            self.thread_local.connection = pika.BlockingConnection(self.connection_params)
            self.thread_local.channel = self.thread_local.connection.channel()
        return self.thread_local.channel

    def close(self):
        if hasattr(self.thread_local, "connection"):
            self.thread_local.connection.close()

    def publish(self, topic, message):
        channel = self._get_channel()
        channel.queue_declare(queue=topic, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=topic,
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)
        )

    def process(self, topic, callback):
        def run():
            channel = self._get_channel()
            channel.queue_declare(queue=topic, durable=True)

            def on_message(ch, method, properties, body):
                try:
                    callback(body)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    print(f"[!] Error: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            channel.basic_consume(queue=topic, on_message_callback=on_message)
            channel.start_consuming()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def get(self, topic):
        channel = self._get_channel()
        method_frame, _, body = channel.basic_get(queue=topic, auto_ack=True)
        return body if method_frame else None
