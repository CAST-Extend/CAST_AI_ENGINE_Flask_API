class Config:
    MODEL_NAME = "gpt-4o-mini"
    MODEL_VERSION = ""
    MODEL_URL = "https://stg1.mmc-dallas-int-non-prod-ingress.mgti.mmc.com/coreapi/openai/v1/deployments/mmc-tech-gpt-4o-mini-128k-2024-07-18/chat/completions"
    MODEL_API_KEY = "6b544676-1695-425b-9417-863cd4f0b088-b95952c6-7710-4fc0-ae3b-8b0690dea7cf"
    MODEL_MAX_INPUT_TOKENS = 128000
    MODEL_MAX_OUTPUT_TOKENS = 16384
    MODEL_INVOCATION_DELAY_IN_SECONDS = 10

    IMAGING_URL = "https://castimaging.mmc.com/"
    IMAGING_API_KEY = ""

    MONGODB_CONNECTION_STRING = "mongodb://svc-aha-dev-mdb:vkHOei6NZcQ3ZCL@db27.usint.dev.db.mmc.com:15695,db28.usint.dev.db.mmc.com:15695,db29.usint.dev.db.mmc.com:15695/ApplicationHDev?authSource=$external&authMechanism=PLAIN&MaxPoolSize=200&socketTimeoutMS=300000&connectTimeoutMS=300000&w=majority&wtimeoutMS=300000&readConcernLevel=majority&replicaSet=ApplicationHeal&tls=true&tlsCAFile=CAroot.pem"
    MONGODB_NAME = "ApplicationHDev"

    # message queue
    MQ_VENDOR = "kafka"  # or "rabbitmq"

    # RabbitMQ Configuration
    RABBITMQ_HOST = "localhost"
    RABBITMQ_PORT = 5672
    RABBITMQ_VHOST = "/"
    RABBITMQ_USER = "guest"
    RABBITMQ_PASSWORD = "guest"

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
    KAFKA_GROUP_ID = "cast_ai_group"
    KAFKA_AUTO_OFFSET_RESET = "earliest"

    MAX_THREADS = 20
    PORT = 8081
