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
        self.db = self.client[config["MONGODB_DATABASE_NAME"]]
        self.lock = threading.Lock()
        self.queue_col = self.db["status_queue"]
        # self.queue_col.drop_index("timestamp")  # Drop the conflicting index
        # self.queue_col.create_index("timestamp", expireAfterSeconds=60)

    def publish(self, topic, message):
        print(f"\n[MongoDBMQ] Publishing message to {topic}: {message}")
        with self.lock:
            if isinstance(message, str):
                try:
                    message_json = json.loads(message)
                except json.JSONDecodeError:
                    message_json = {"message": message}
            else:
                message_json = message

            request_id = message_json.get("request_id")
            # message_json["timestamp"] = time.time()

            if request_id:
                existing_doc = self.db[topic].find_one({"request_id": request_id})
                current_status = existing_doc.get("status") if existing_doc else None
                new_status = message_json.get("status")

                if current_status in ["queued", "processing"] and new_status == "queued":
                    print(f"\n[MongoDBMQ] Skipping re-queue: request {request_id} already in status '{current_status}'")
                    return

                self.db[topic].replace_one(
                    {"request_id": request_id},
                    message_json,
                    upsert=True
                )
                print(f"\n[MongoDBMQ] Request {request_id} updated to status '{new_status}'")
            else:
                self.db[topic].insert_one(message_json)

    def get(self, topic, filter_by=None):
        query = filter_by if filter_by else {"status": "queued"}
        doc = self.db[topic].find_one(query)
        if doc:
            print(f"\n[MongoDBMQ] Fetched from {topic}: {doc}")
        return doc

    def update_status(self, topic, request_id, new_status):
        result = self.db[topic].update_one(
            {"request_id": request_id, "status": "queued"},
            {"$set": {"status": new_status}}
        )
        if result.modified_count == 1:
            print(f"\n[MongoDBMQ] Updated request {request_id} to status '{new_status}'")
            return True
        else:
            print(f"\n[MongoDBMQ] Failed to update request {request_id} to '{new_status}' (possibly already processed)")
            return False

    def get_latest_status(self, topic, request_id):
        doc = self.db[topic].find({"request_id": request_id})
        doc = list(doc)
        if doc:
            print(f"\n[MongoDBMQ] Latest status for {request_id}: {doc[0]}")
            return doc[0]
        return None

    def close(self):
        self.client.close()

    @property
    def db_connection(self):
        return self.db