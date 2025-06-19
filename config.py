class Config:
    # Model configs...
    MODEL_NAME = "gpt-4o-mini"
    MODEL_VERSION = "null"
    MODEL_URL = "null"
    MODEL_API_KEY = "null"
    MODEL_MAX_INPUT_TOKENS = 128000
    MODEL_MAX_OUTPUT_TOKENS = 16384
    MODEL_INVOCATION_DELAY_IN_SECONDS = 10

    # Imaging configs...
    IMAGING_URL = "null"
    IMAGING_API_KEY = ""

    # MongoDB configs...
    MONGODB_CONNECTION_STRING = "mongodb://localhost:27017"
    MONGODB_DATABASE_NAME = "cast_queue_db"

    # Use queue mechanism
    MQ_VENDOR = "mongodb"  # or "kafka" or "rabbitmq"

    # RabbitMQ configs (if used)
    RABBITMQ_HOST = "localhost"
    RABBITMQ_PORT = 5672
    RABBITMQ_VHOST = "/"
    RABBITMQ_USER = "guest"
    RABBITMQ_PASSWORD = "guest"

    # Kafka configs (if used)
    KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
    KAFKA_GROUP_ID = "cast_ai_group"
    KAFKA_AUTO_OFFSET_RESET = "earliest"

    MAX_THREADS = 20
    PORT = 8081
