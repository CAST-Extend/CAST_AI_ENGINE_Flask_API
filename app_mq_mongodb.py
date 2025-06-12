from base_mq import BaseMQ
from flask import Config as FlaskConfig
from pymongo import MongoClient
import threading
import time
import json

class MongoDBMQ(BaseMQ):
    def __init__(self, config: FlaskConfig):
        self.config = config
        self.client = MongoClient(config["MONGODB_CONNECTION_STRING"])
        self.db = self.client[config["MONGODB_NAME"]]
        self.lock = threading.Lock()

        for topic in ['request_queue', 'status_queue']:
            self.db[topic].create_index("timestamp", expireAfterSeconds=86400)

    def publish(self, topic, message):
        print(f"[MongoDBMQ] Publishing message to {topic}: {message}")
        with self.lock:
            if isinstance(message, str):
                try:
                    message_json = json.loads(message)
                except json.JSONDecodeError:
                    message_json = {"message": message}
            else:
                message_json = message

            request_id = message_json.get("request_id") or message_json.get("message") or None

            doc = {
                "message": message,
                "status": "queued",
                "timestamp": time.time()
            }

            if request_id:
                doc["request_id"] = request_id

            self.db[topic].insert_one(doc)

    def get(self, topic, filter_by=None):
        query = filter_by if filter_by else {}
        doc = self.db[topic].find_one(query)
        if doc:
            print(f"[MongoDBMQ] Peeked from {topic}: {doc['message']}")
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
