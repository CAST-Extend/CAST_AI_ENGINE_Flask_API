# app_mq_mongodb.py

from base_mq import BaseMQ
from flask import Config as FlaskConfig
from pymongo import MongoClient
import threading
import time

class MongoDBMQ(BaseMQ):
    def __init__(self, config: FlaskConfig):
        self.config = config
        self.client = MongoClient(config["MONGODB_CONNECTION_STRING"])
        self.db = self.client[config["MONGODB_NAME"]]
        self.lock = threading.Lock()

        # Optional: create TTL index for 1-day cleanup
        for topic in ['request_queue', 'status_queue']:
            self.db[topic].create_index("timestamp", expireAfterSeconds=86400)

    def publish(self, topic, message):
        print(f"[MongoDBMQ] Publishing message to {topic}: {message}")
        with self.lock:
            self.db[topic].insert_one({
                "message": message,
                "status": "queued",
                "timestamp": time.time()
            })

    def get(self, topic):
        doc = self.db[topic].find_one_and_delete({})
        if doc:
            print(f"[MongoDBMQ] Fetched from {topic}: {doc['message']}")
        return doc["message"] if doc else None

    def process(self, topic, callback):
        def run():
            print(f"[MongoDBMQ] Starting processor for topic: {topic}")
            while True:
                doc = self.db[topic].find_one_and_delete({})
                if doc:
                    try:
                        print(f"[MongoDBMQ] Processing message: {doc['message']}")
                        callback(doc["message"])
                    except Exception as e:
                        print(f"[MongoDBMQ] Processing error: {e}")
                else:
                    time.sleep(1)
        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def close(self):
        self.client.close()
