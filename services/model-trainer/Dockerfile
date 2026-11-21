# Training Job (UC7, ADR 0005). Build from the REPO ROOT:
#   docker build -f services/model-trainer/Dockerfile -t model-trainer .
#   docker run --rm model-trainer --no-db
# with the docker-compose Postgres on your laptop:
#   docker run --rm -e DATABASE_URL=postgresql://model_trainer:dev_model_trainer@host.docker.internal:5432/sleep_apnea model-trainer
# --model fast for the fast model; F1 gate: docker run --rm --entrypoint python model-trainer services/model-trainer/gate.py
# the file goes to /app/models/ inside the container (mount -v "$PWD/models:/app/models" to keep it)
# numpy 2.5 needs Python 3.12+
FROM python:3.12-slim

WORKDIR /app
COPY services/model-trainer/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# shared feature code + the training script + the cleaned nights
COPY services/common/ services/common/
COPY services/model-trainer/train.py services/model-trainer/gate.py services/model-trainer/
COPY data/clean/ data/clean/

ENV PYTHONPATH=/app/services/common \
    DATABASE_URL=postgresql://model_trainer:dev_model_trainer@postgres:5432/sleep_apnea \
    REGION=AT \
    TRIGGERED_BY=manual

ENTRYPOINT ["python", "services/model-trainer/train.py"]
