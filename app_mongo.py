from motor.motor_asyncio import AsyncIOMotorClient
from flask import Config as FlaskConfig

class AppMongoDb:
    def __init__(self, config: FlaskConfig):
        self.client = AsyncIOMotorClient(config["MONGODB_CONNECTION_STRING"])
        self.db = self.client[config["MONGODB_NAME"]]

    async def get_collection(self, collection_name):
        return self.db[collection_name]

    async def list_collections(self):
        return await self.db.list_collection_names()
