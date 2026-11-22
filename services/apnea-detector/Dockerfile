# apnea-detector (UC2, UC3 alert check, UC5). Build from the REPO ROOT:
#   docker build -f services/apnea-detector/Dockerfile -t apnea-detector .
# kind: build with the tag apnea-detector:dev, then  kind load docker-image apnea-detector:dev --name apnea  (k8s/README.md)
# models/model.joblib must exist first (the fast model is a rule, services/common/fast_model.py):
#   python services/model-trainer/train.py --no-db
# Python 3.12 (3.12-3.14 work, see requirements.txt)
FROM python:3.12-slim

WORKDIR /app
COPY services/apnea-detector/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# shared feature code (same as in training), the service, the message schemas, the models
COPY services/common/ services/common/
COPY services/apnea-detector/*.py services/apnea-detector/
COPY kafka/schemas/ kafka/schemas/
COPY models/ models/

ENV PYTHONPATH=/app/services/common \
    MODEL_PATH=/app/models/model.joblib \
    SCHEMA_DIR=/app/kafka/schemas \
    KAFKA_BOOTSTRAP=kafka:29092 \
    DATABASE_URL=postgresql://apnea_detector:dev_apnea_detector@postgres:5432/sleep_apnea \
    METRICS_PORT=8000

# Prometheus /metrics
EXPOSE 8000
USER nobody
ENTRYPOINT ["python", "services/apnea-detector/detector.py"]
