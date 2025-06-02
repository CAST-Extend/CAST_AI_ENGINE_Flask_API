class Config:
    MODEL_NAME = "gpt-4o-mini"
    MODEL_VERSION = "null"
    MODEL_URL = "null"
    MODEL_API_KEY = "null"
    MODEL_MAX_INPUT_TOKENS = 128000
    MODEL_MAX_OUTPUT_TOKENS = 16384
    MODEL_INVOCATION_DELAY_IN_SECONDS = 10

    IMAGING_URL = "null"
    IMAGING_API_KEY = ""

    MONGODB_CONNECTION_STRING = "null"
    MONGODB_NAME = "null"

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
