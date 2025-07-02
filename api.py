# === Updated api.py ===
import multiprocessing
import requests
import warnings
import json
import time

from flask import Flask, jsonify, request
from flask_cors import CORS
from app_imaging import AppImaging
from app_llm import AppLLM
from app_logger import AppLogger
from app_code_fixer import AppCodeFixer
from app_mongo import AppMongoDb
from app_mq import AppMessageQueue
from config import Config
from threading import Thread
from utils import get_timestamp
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

app = Flask(__name__)
CORS(app)
app.config.from_object(Config)

mongo_db = AppMongoDb(app.config)
app_logger = AppLogger(mongo_db)
ai_model = AppLLM(app_logger, app.config)
imaging = AppImaging(app_logger, app.config)
code_fixer = AppCodeFixer(app_logger, mongo_db, ai_model, imaging)

def reset_processing_to_queued():
    try:
        mongo_db = AppMongoDb(app.config)
        collection = mongo_db.get_collection("status_queue")

        result = collection.update_many(
            {"status": "processing"},
            {"$set": {"status": "queued"}}
        )
        print(f"Changed {result.modified_count} document(s) status from 'processing' to 'queued'....................................................................")
    except Exception as e:
        print("Error while executing function reset_processing_to_queued():- ", str(e))

def get_mq():
    return AppMessageQueue(app_logger, app.config).open()

def request_worker():
    queue = get_mq()
    print('\n[WORKER] Background thread processor started.')

    while True:
        try:
            doc = queue.get("status_queue", filter_by={"status": "queued"})
            if doc:
                request_id = doc.get("request_id")
                # retry_count = int(doc.get("retry_count", 0)) + 1

                success = queue.update_status("status_queue", request_id, "processing")
                if not success:
                    time.sleep(0.5)
                    continue  # Another thread may have taken it

                print(f"\n[WORKER] Processing: {request_id}")

                start_datetime = get_timestamp()

                result = code_fixer.process_request_logic(request_id, mongo_db)
                status = "completed" if result.get("status") == "success" else "failed"

                end_datetime = get_timestamp()

                # Step 3: Fetch the document
                collection = mongo_db.get_collection("status_queue")
                doc = collection.find_one({"request_id": request_id})

                if doc:
                    #Update the document in MongoDB
                    result = collection.update_one(
                        {"request_id": request_id},
                        {"$set": { "status": status, "start_datetime": start_datetime, "end_datetime": end_datetime}}
                    )

            else:
                # print("\n[WORKER DEBUG] No queued document found in status_queue. Possible reasons: empty queue, filter mismatch, or race condition.")
                time.sleep(1)

        except Exception as e:
            print(f"\n[WORKER ERROR] {e}")
            time.sleep(2)

@app.route("/api-python/v1/")
def home():
    return {"status": 200, "success": "Welcome to CAST Code Fix AI ENGINE."}, 200

@app.route("/api-python/v1/CheckMongoDBConnection")
def check_mongodb_connection():
    try:
        mongo_db = AppMongoDb(app.config)
        mongodb_collections = mongo_db.list_collections()
        return {"status": 200, "collections": mongodb_collections}, 200
    except Exception as e:
        return {"status": 500, "error": str(e)}, 500

@app.route("/api-python/v1/ProcessRequest/<string:request_id>")
def process_request(request_id):
    try:
        queue = get_mq()
        queue.publish("status_queue", {
            "request_id": request_id,
            "status": "queued",
            # "retry_count": 0,
            # "timestamp": time.time()
        })
        return {
            "Request_Id": request_id,
            "status": "queued",
            "message": "Request has been enqueued for processing.",
            "code": 202
        }
    except Exception as e:
        print(f"[ERROR] {e}")
        return {"status": "error", "message": str(e), "code": 500}, 500

@app.route("/api-python/v1/RequestStatus/<string:request_id>")
def get_request_status(request_id):
    try:
        queue = get_mq()
        latest_doc = queue.db["status_queue"].find_one({"request_id": request_id}, sort=[("timestamp", -1)])
        if not latest_doc:
            return {
                "Request_Id": request_id,
                "status": "not_found",
                "message": "No status found for this request ID",
                "code": 404
            }
        return {
            "Request_Id": request_id,
            "status": latest_doc.get("status", "unknown"),
            # "retry_count": latest_doc.get("retry_count", 0),
            # "last_updated": latest_doc.get("timestamp"),
            # "response": latest_doc.get("response", {}),
            "code": 200
        }
    except Exception as e:
        print(f"[ERROR] Failed to get status for {request_id}: {e}")
        return {"status": "error", "message": str(e), "code": 500}, 500

@app.route("/api-python/v1/ListPendingRequests")
def list_pending_requests():
    try:
        queue = get_mq()
        pending_cursor = queue.db["status_queue"].find({"status": "queued"})
        pending = []
        for doc in pending_cursor:
            pending.append({
                "request_id": doc.get("request_id"),
                "status": doc.get("status"),
                "timestamp": doc.get("timestamp")
            })
        return {"status": 200, "pending_requests": pending}, 200
    except Exception as e:
        print(f"[ERROR] Listing pending requests: {e}")
        return {"status": "error", "message": str(e), "code": 500}, 500

if __name__ == "__main__":
    reset_processing_to_queued()  # run only once on startup

    worker_threads = []
    cpu_count = multiprocessing.cpu_count()
    NUM_WORKERS = min(2 * cpu_count, int(app.config["MAX_THREADS"]))

    print(f"Total number of CPU Cores - {cpu_count}")
    print(f"Total number of workers created - {NUM_WORKERS}")

    for _ in range(NUM_WORKERS):
        worker_thread = Thread(target=request_worker, daemon=True)
        worker_thread.start()
        worker_threads.append(worker_thread)

    app.run(debug=False, host="0.0.0.0", port=app.config["PORT"])