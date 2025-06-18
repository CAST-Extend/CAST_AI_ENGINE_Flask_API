# === Updated app_mq_mongodb.py ===
from flask import Config as FlaskConfig
from pymongo import MongoClient
import threading
import time
import json

class MongoDBMQ:
    def __init__(self, config: FlaskConfig):
        self.config = config
        self.client = MongoClient(config["MONGODB_CONNECTION_STRING"])
        self.db = self.client[config["MONGODB_NAME"]]
        self.lock = threading.Lock()
        self.queue_col = self.db["status_queue"]
        self.queue_col.create_index("timestamp", expireAfterSeconds=86400)

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

            request_id = message_json.get("request_id")
            message_json["timestamp"] = time.time()

            if request_id:
                self.db[topic].replace_one(
                    {"request_id": request_id},
                    message_json,
                    upsert=True
                )
            else:
                self.db[topic].insert_one(message_json)

    def get(self, topic, filter_by=None):
        query = filter_by if filter_by else {}
        doc = self.db[topic].find_one_and_update(
            query,
            {"$set": {"status": "processing", "processing_start": time.time()}},
            sort=[("timestamp", 1)]
        )
        if doc:
            print(f"[MongoDBMQ] Picked from {topic}: {doc}")
        return doc

    def get_latest_status(self, topic, request_id):
        doc = self.db[topic].find({"request_id": request_id}).sort("timestamp", -1).limit(1)
        doc = list(doc)
        if doc:
            print(f"[MongoDBMQ] Latest status for {request_id}: {doc[0]}")
            return doc[0]
        return None

    def close(self):
        self.client.close()

    @property
    def db_connection(self):
        return self.db