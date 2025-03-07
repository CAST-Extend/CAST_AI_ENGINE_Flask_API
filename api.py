import multiprocessing
import requests
import warnings

from flask import Flask, jsonify
from flask_cors import CORS
from app_imaging import AppImaging
from app_llm import AppLLM
from app_logger import AppLogger
from app_code_fixer import AppCodeFixer
from app_mongo import AppMongoDb
from config import Config
from queue import Queue
from threading import Thread, Lock
from requests.packages.urllib3.exceptions import InsecureRequestWarning # type: ignore

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
    category = FutureWarning,
    message = "`clean_up_tokenization_spaces` was not set.*",
)

# ============ THREADS AND QUEUE MANAGEMENT ============

# Global request queue
request_queue = Queue()
queue_status = {}
queue_lock = Lock()

# Worker function to process requests
def request_worker():
    while True:
        request_id = request_queue.get()  # Fetch next request from the queue
        if request_id is None:
            # REM-DMA: should we call request_queue.task_done()?
            break  # Exit the loop if a None signal is sent
        
        with queue_lock:
            queue_status[request_id] = "Processing"
        
        try:
            # Call the original process_request logic here
            response = code_fixer.process_request_logic(request_id)
            with queue_lock:
                queue_status[request_id] = "Completed"
            print(f"Request {request_id} processed successfully: {response}")
        except Exception as e:
            with queue_lock:
                queue_status[request_id] = "Failed"
            print(f"Error processing request {request_id}: {e}")
        finally:
            request_queue.task_done()  # Mark the task as done

# Start multiple worker threads
worker_threads = []

cpu_count = multiprocessing.cpu_count()  # Get the number of CPU cores
print(f"Total number of CPU Cores - {cpu_count}")
# You can use a multiplier to adjust the number of threads (e.g., 2 x CPU cores)
# Limit to a maximum of workers to avoid excessive threads (configurable)
NUM_WORKERS = min(2 * cpu_count, app.config["MAX_THREADS"])  
print(f"Total number of threads created - {NUM_WORKERS}")
for _ in range(NUM_WORKERS):
    worker_thread = Thread(target=request_worker, daemon=True)
    worker_thread.start()
    worker_threads.append(worker_thread)

# ============ ROUTES ============

@app.route("/api-python/v1/")
def home():
    return {
        "status": 200,
        "success" : "Welcome to CAST Code Fix AI ENGINE."
    }, 200

@app.route("/api-python/v1/ProcessRequest/<string:Request_Id>")
def process_request(Request_Id):
    with queue_lock:
        if queue_status.get(Request_Id) == "Processing":
            return jsonify({
                "Request_Id": Request_Id,
                "status": "in_progress",
                "message": f"Request {Request_Id} is already being processed.",
                "code": 202,
                "num_of_cpu": cpu_count,
                "num_of_threads_created": NUM_WORKERS
            })
        elif queue_status.get(Request_Id) == "Completed":
            return jsonify({
                "Request_Id": Request_Id,
                "status": "completed",
                "message": f"Request {Request_Id} has already been processed.",
                "code": 200,
                "num_of_cpu": cpu_count,
                "num_of_threads_created": NUM_WORKERS
            }), 200
        elif queue_status.get(Request_Id) == "Failed":
            return jsonify({
                "Request_Id": Request_Id,
                "status": "failed",
                "message": f"Request {Request_Id} failed during processing.",
                "code": 500,
                "num_of_cpu": cpu_count,
                "num_of_threads_created": NUM_WORKERS
            }), 500
        else:
            # Add the request to the queue
            queue_status[Request_Id] = "Queued"
            request_queue.put(Request_Id)
            return jsonify({
                "Request_Id": Request_Id,
                "status": "queued",
                "message": f"Request {Request_Id} has been added to the processing queue.",
                "code": 202,
                "num_of_cpu": cpu_count,
                "num_of_threads_created": NUM_WORKERS
            })

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=app.config["PORT"])
