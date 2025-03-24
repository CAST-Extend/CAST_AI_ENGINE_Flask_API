import pika
import multiprocessing
import requests
import warnings
import json

from flask import Flask, jsonify
from flask_cors import CORS
from app_imaging import AppImaging
from app_llm import AppLLM
from app_logger import AppLogger
from app_code_fixer import AppCodeFixer
from app_mongo import AppMongoDb
from config import Config
from threading import Thread
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

# ============ RABBITMQ SETUP ============

def get_rabbitmq_connection():
    credentials = pika.PlainCredentials(
        app.config.get("RABBITMQ_USER", "guest"),
        app.config.get("RABBITMQ_PASSWORD", "guest")
    )
    parameters = pika.ConnectionParameters(
        host=app.config.get("RABBITMQ_HOST", "localhost"),
        port=app.config.get("RABBITMQ_PORT", 5672),
        virtual_host=app.config.get("RABBITMQ_VHOST", "/"),
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    return pika.BlockingConnection(parameters)

def declare_queues(channel):
    channel.queue_declare(queue='request_queue', durable=True)
    channel.queue_declare(queue='status_queue', durable=True)

# Worker function to process requests
def request_worker():
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    declare_queues(channel)
    
    def callback(ch, method, properties, body):
        try:
            request_id = body.decode()
            print(f"Processing request {request_id}")
            
            # Update status to Processing
            channel.basic_publish(
                exchange='',
                routing_key='status_queue',
                body=json.dumps({
                    'request_id': request_id,
                    'status': 'Processing'
                }),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                ))
            
            # Process the request
            response = code_fixer.process_request_logic(request_id)
            
            # Update status based on result
            status = 'Completed' if response.get('status') == 'success' else 'Failed'
            channel.basic_publish(
                exchange='',
                routing_key='status_queue',
                body=json.dumps({
                    'request_id': request_id,
                    'status': status,
                    'response': response
                }),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                ))
            
            ch.basic_ack(delivery_tag=method.delivery_tag)
            print(f"Request {request_id} processed successfully")
            
        except Exception as e:
            print(f"Error processing request: {e}")
            # Update status to Failed
            channel.basic_publish(
                exchange='',
                routing_key='status_queue',
                body=json.dumps({
                    'request_id': request_id,
                    'status': 'Failed',
                    'error': str(e)
                }),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent,
                ))
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='request_queue', on_message_callback=callback)
    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()

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
        "success" : "Welcome to CAST Code Fix AI ENGINE."
    }, 200

@app.route("/api-python/v1/CheckMongoDBConnection")
def check_mongodb_connection():
    try:
        mongo_db = AppMongoDb(app.config)
        mongodb_collections = mongo_db.list_collections()
        
        return {
            "status": 200,
            "success" : "Connection to MongoDB successful!",
            "mongodb_collections" : mongodb_collections
        }, 200
    
    except Exception as e:
        print(f"Connection to MongoDB failed: {e}")
        return {
            "status": 500,
            "failed" : f"Connection to MongoDB failed: {e}"
        }, 500

@app.route("/api-python/v1/ProcessRequest/<string:Request_Id>")
def process_request(Request_Id):
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        declare_queues(channel)
        
        # Check current status
        method_frame, header_frame, body = channel.basic_get(queue='status_queue', auto_ack=True)
        
        if method_frame:
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
        
        # If not found in status queue, add to request queue
        channel.basic_publish(
            exchange='',
            routing_key='request_queue',
            body=Request_Id,
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            ))
        
        # Update status to Queued
        channel.basic_publish(
            exchange='',
            routing_key='status_queue',
            body=json.dumps({
                'request_id': Request_Id,
                'status': 'Queued'
            }),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            ))
        
        connection.close()
        
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

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=app.config["PORT"])
