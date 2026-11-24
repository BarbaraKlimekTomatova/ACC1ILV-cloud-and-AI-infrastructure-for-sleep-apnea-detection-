# device-simulator (UC1). Build from the REPO ROOT, from a clean git checkout (nothing to
# generate first):
#   docker build -f services/device-simulator/Dockerfile -t device-simulator .
#   kind:  ... -t device-simulator:dev .  then  kind load docker-image device-simulator:dev --name apnea
# The Kafka messages are not in git. Stage 1 makes them from data/clean/ (in git) with
# data/03_to_kafka_messages.py, stage 2 is the service with only those .jsonl files.
#   --build-arg SPLIT=demo   the 5 demo nights P01-P05 (default, ~10 MB)
#   --build-arg SPLIT=all    all 33 nights (then run with ALL_NIGHTS=1 or name the nights)
# Run (Kafka from docker compose):
#   docker run --rm --network <compose-network> device-simulator --speed 60
#   docker run --rm --network <compose-network> -e BURST=1 -e COPIES=4 device-simulator
# In Kubernetes: k8s/jobs/device-simulator.yaml
# Python 3.12 (3.12-3.14 work, see requirements.txt)

# ---------------------------------------------------------------- 1. make the messages
FROM python:3.12-slim AS messages
WORKDIR /src
RUN pip install --no-cache-dir numpy==2.5.4
COPY data/03_to_kafka_messages.py data/
COPY data/clean/splits.json data/clean/
COPY data/clean/signals/ data/clean/signals/
ARG SPLIT=demo
RUN if [ "$SPLIT" = "all" ]; then python data/03_to_kafka_messages.py; \
    else python data/03_to_kafka_messages.py --split "$SPLIT"; fi \
 && test -n "$(ls kafka/messages/raw-signals/*.jsonl)"

# ---------------------------------------------------------------- 2. the service
FROM python:3.12-slim

WORKDIR /app
COPY services/device-simulator/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# the service, the message schema, the nights (one .jsonl per night, from stage 1)
COPY services/device-simulator/main.py services/device-simulator/
COPY kafka/schemas/ kafka/schemas/
COPY --from=messages /src/kafka/messages/raw-signals/ kafka/messages/raw-signals/

ENV SCHEMA_DIR=/app/kafka/schemas \
    MESSAGES_DIR=/app/kafka/messages/raw-signals \
    KAFKA_BOOTSTRAP=kafka:29092 \
    SPEED=60 \
    PYTHONUNBUFFERED=1

USER nobody
ENTRYPOINT ["python", "services/device-simulator/main.py"]
