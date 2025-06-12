class BaseMQ:
    async def close(self):
        raise NotImplementedError()

    async def publish(self, topic, message):
        raise NotImplementedError()

    async def get(self, topic):
        raise NotImplementedError()
