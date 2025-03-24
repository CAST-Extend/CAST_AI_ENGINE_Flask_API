from flask import Config as FlaskConfig
from pymongo import MongoClient

class AppMongoDb:
    def __init__(self, config: FlaskConfig):
        self.connection_string = config["MONGODB_CONNECTION_STRING"]
        self.mongodb_name = config["MONGODB_NAME"]
        self.client = MongoClient(self.connection_string)

    def get_collection(self, collection_name):
        # Example of accessing a specific database (replace 'mydatabase' with your DB name)
        db = self.client[self.mongodb_name]
        return db[collection_name]
    
    def list_collections(self):
        db = self.client[self.mongodb_name]
        return db.list_collection_names()
