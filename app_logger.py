import logging
import traceback



class AppLogger:
    from app_mongo import AppMongoDb
    def __init__(self, mongo_db: AppMongoDb):
        self.mongo_db = mongo_db

    def log_error(self, function_name, exception):
        from utils import get_timestamp
        collection = self.mongo_db.get_collection("ExceptionLog")
        error_data = {
            "function": function_name,
            "error": str(exception),
            "trace": traceback.format_exc(),
            "timestamp": get_timestamp(),
        }
        collection.insert_one(error_data)
        logging.error(f"Error logged to MongoDB: {error_data}\n")
