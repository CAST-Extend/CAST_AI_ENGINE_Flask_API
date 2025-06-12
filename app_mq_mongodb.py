# app_mq_mongodb.py

from base_mq import BaseMQ
from motor.motor_asyncio import AsyncIOMotorClient
from flask import Config as FlaskConfig
import time

class MongoDBMQ(BaseMQ):
    def __init__(self, config: FlaskConfig):
        self.config = config
        self.client = AsyncIOMotorClient(config["MONGODB_CONNECTION_STRING"])
        self.db = self.client[config["MONGODB_NAME"]]

    async def publish(self, topic, message):
        await self.db[topic].insert_one({
            "message": message,
            "status": "queued",
            "timestamp": time.time()
        })

    async def get(self, topic):
        doc = await self.db[topic].find_one_and_delete({})
        return doc["message"] if doc else None

    async def close(self):
        self.client.close()
