import multiprocessing
import requests
import warnings
import json

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
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Suppress the InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

# Load configuration from config.py
app.config.from_object(Config)

# Initialize components
mongo_db = AppMongoDb(app.config)
app_logger = AppLogger(mongo_db)
ai_model = AppLLM(app_logger, app.config)
imaging = AppImaging(app_logger, app.config)
code_fixer = AppCodeFixer(app_logger, mongo_db, ai_model, imaging)

# Suppress specific FutureWarning
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message="`clean_up_tokenization_spaces` was not set.*",
)

# MQ helper to avoid shared instance
def get_mq():
    return AppMessageQueue(app_logger, app.config).open()

# Worker function to process requests
def request_worker():
    queue = None
    try:
        queue = get_mq()

        def callback(message):
            try:
                request_id = message.decode() if isinstance(message, bytes) else message
                print(f"Processing request {request_id}")

                # Update status to Processing
                queue.publish(
                    topic='status_queue',
                    message=json.dumps({
                        'request_id': request_id,
                        'status': 'Processing'
                    })
                )

                # Process the request
                response = code_fixer.process_request_logic(request_id)

                # Update status based on result
                status = 'Completed' if response.get('status') == 'success' else 'Failed'
                queue.publish(
                    topic='status_queue',
                    message=json.dumps({
                        'request_id': request_id,
                        'status': status,
                        'response': response
                    })
                )

                print(f"Request {request_id} processed successfully")

            except Exception as e:
                fallback_request_id = request_id if 'request_id' in locals() else 'unknown'
                queue.publish(
                    topic='status_queue',
                    message=json.dumps({
                        'request_id': fallback_request_id,
                        'status': 'Failed',
                        'error': str(e)
                    })
                )
                raise

        print(' [*] Waiting for messages. To exit press CTRL+C')
        queue.process(topic='request_queue', callback=callback)

    except Exception as err:
        print(f' [*] Worker thread failed with {type(err)=}: {err=}')
        if queue is not None:
            queue.close()

# Start multiple worker threads
worker_threads = []
cpu_count = multiprocessing.cpu_count()
NUM_WORKERS = min(2 * cpu_count, app.config["MAX_THREADS"])

print(f"Total number of CPU Cores - {cpu_count}")
print(f"Total number of workers created - {NUM_WORKERS}")

for _ in range(NUM_WORKERS):
    worker_thread = Thread(target=request_worker, daemon=True)
    worker_thread.start()
    worker_threads.append(worker_thread)

# ============ ROUTES ============

@app.route("/api-python/v1/")
def home():
    return {
        "status": 200,
        "success": "Welcome to CAST Code Fix AI ENGINE."
    }, 200

@app.route("/api-python/v1/CheckMongoDBConnection")
def check_mongodb_connection():
    try:
        mongo_db = AppMongoDb(app.config)
        mongodb_collections = mongo_db.list_collections()

        return {
            "status": 200,
            "success": "Connection to MongoDB successful!",
            "mongodb_collections": mongodb_collections
        }, 200

    except Exception as e:
        print(f"Connection to MongoDB failed: {e}")
        return {
            "status": 500,
            "failed": f"Connection to MongoDB failed: {e}"
        }, 500

@app.route("/api-python/v1/ProcessRequest/<string:Request_Id>")
def process_request(Request_Id):
    queue = None
    try:
        queue = get_mq()

        # Check if already exists in status_queue
        existing_status = queue.get(topic='status_queue', filter_by={"request_id": Request_Id})
        if existing_status:
            status_message = json.loads(existing_status)
            status = status_message['status']
            response_data = {
                "Request_Id": Request_Id,
                "status": status.lower(),
                "message": f"Request {Request_Id} is {status}",
                "code": 202 if status == 'Processing' else 200 if status == 'Completed' else 500,
                "num_of_cpu": cpu_count,
                "num_of_threads_created": NUM_WORKERS
            }
            if 'response' in status_message:
                response_data.update(status_message['response'])
            return jsonify(response_data)

        # If new, publish
        print(f"[API] Publishing {Request_Id} to request_queue")
        queue.publish(topic='request_queue', message=Request_Id)

        print(f"[API] Publishing status 'Queued' for {Request_Id}")
        queue.publish(
            topic='status_queue',
            message=json.dumps({
                'request_id': Request_Id,
                'status': 'Queued'
            })
        )

        return jsonify({
            "Request_Id": Request_Id,
            "status": "queued",
            "message": f"Request {Request_Id} has been added to the processing queue.",
            "code": 202,
            "num_of_cpu": cpu_count,
            "num_of_threads_created": NUM_WORKERS
        })

    except Exception as e:
        return jsonify({
            "Request_Id": Request_Id,
            "status": "failed",
            "message": f"Error processing request: {str(e)}",
            "code": 500,
            "num_of_cpu": cpu_count,
            "num_of_threads_created": NUM_WORKERS
        }), 500

    finally:
        if queue is not None:
            queue.close()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=app.config["PORT"])
