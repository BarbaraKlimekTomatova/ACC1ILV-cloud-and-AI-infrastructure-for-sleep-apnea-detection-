# alert-service (UC3). Build from the REPO ROOT:
#   docker build -f services/alert-service/Dockerfile -t alert-service .
FROM python:3.12-slim

WORKDIR /app
COPY services/alert-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/alert-service/alert_service.py services/alert-service/
COPY kafka/schemas/ kafka/schemas/

ENV SCHEMA_DIR=/app/kafka/schemas \
    KAFKA_BOOTSTRAP=kafka:29092 \
    DATABASE_URL=postgresql://alert_service:dev_alert_service@postgres:5432/sleep_apnea \
    METRICS_PORT=8003 \
    PYTHONUNBUFFERED=1

# Prometheus /metrics
EXPOSE 8003
USER nobody
ENTRYPOINT ["python", "services/alert-service/alert_service.py"]
