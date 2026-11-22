# device-simulator (UC1). Build from the REPO ROOT:
#   docker build -f services/device-simulator/Dockerfile -t device-simulator .
# The messages are generated, not in git, so make them first:
#   python data/03_to_kafka_messages.py --split demo     (or without --split for all 33 nights)
# Run (Kafka from docker compose):
#   docker run --rm --network <compose-network> device-simulator --speed 60
#   docker run --rm --network <compose-network> -e BURST=1 -e COPIES=4 device-simulator
# Python 3.12 (3.12-3.14 work, see requirements.txt)
FROM python:3.12-slim

WORKDIR /app
COPY services/device-simulator/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# the service, the message schema, the nights (one .jsonl per night)
COPY services/device-simulator/main.py services/device-simulator/
COPY kafka/schemas/ kafka/schemas/
COPY kafka/messages/raw-signals/ kafka/messages/raw-signals/

ENV SCHEMA_DIR=/app/kafka/schemas \
    MESSAGES_DIR=/app/kafka/messages/raw-signals \
    KAFKA_BOOTSTRAP=kafka:29092 \
    SPEED=60 \
    PYTHONUNBUFFERED=1

USER nobody
ENTRYPOINT ["python", "services/device-simulator/main.py"]
