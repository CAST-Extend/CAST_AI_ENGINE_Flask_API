import asyncio
import json
import multiprocessing
import warnings

from flask import Flask, jsonify
from flask_cors import CORS
from app_imaging import AppImaging
from app_llm import AppLLM
from app_logger import AppLogger
from app_code_fixer import AppCodeFixer
from app_mongo import AppMongoDb  # You will need to update this to motor-based MongoDB client separately
from app_mq import AppMessageQueue
from config import Config

# Suppress warnings
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message="`clean_up_tokenization_spaces` was not set.*",
)

app = Flask(__name__)
CORS(app)
app.config.from_object(Config)

# Initialize components (Assuming synchronous interfaces for now)
mongo_db = AppMongoDb(app.config)
app_logger = AppLogger(mongo_db)
ai_model = AppLLM(app_logger, app.config)
imaging = AppImaging(app_logger, app.config)
code_fixer = AppCodeFixer(app_logger, mongo_db, ai_model, imaging)

cpu_count = multiprocessing.cpu_count()
NUM_WORKERS = min(2 * cpu_count, app.config["MAX_THREADS"])

async def process_message_async(queue, message):
    request_id = message.decode() if isinstance(message, bytes) else message
    print(f"Processing request (async) {request_id}")

    # Update status to Processing
    queue.publish(
        topic='status_queue',
        message=json.dumps({
            'request_id': request_id,
            'status': 'Processing'
        })
    )

    # Process the request synchronously here, if possible adapt code_fixer to async
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
    print(f"Request {request_id} processed successfully (async)")

async def worker_loop(queue):
    print(f"Worker loop started (async)")
    while True:
        # Try to get a message non-blocking or with timeout
        msg = queue.get(topic='request_queue')
        if msg:
            try:
                await process_message_async(queue, msg)
            except Exception as e:
                print(f"Error processing message: {e}")
        else:
            # No message, sleep a bit to prevent busy loop
            await asyncio.sleep(1)

def get_mq():
    # MQ interface is still synchronous here; ideally replace with async version if possible
    return AppMessageQueue(app_logger, app.config).open()

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

        body = queue.get(topic='status_queue')

        if body is not None:
            status_message = json.loads(body)
            if status_message['request_id'] == Request_Id:
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

async def main():
    queue = get_mq()
    tasks = []
    for _ in range(NUM_WORKERS):
        tasks.append(asyncio.create_task(worker_loop(queue)))
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    import uvicorn
    # Start background workers and then run Flask app using uvicorn for async support
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    uvicorn.run(app, host="0.0.0.0", port=app.config["PORT"])
