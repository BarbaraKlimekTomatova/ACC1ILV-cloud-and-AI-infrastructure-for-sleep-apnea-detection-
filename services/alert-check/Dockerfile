# alert-check (UC3). Build from the REPO ROOT:
#   docker build -f services/alert-check/Dockerfile -t alert-check .
FROM python:3.12-slim

WORKDIR /app
COPY services/alert-check/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/alert-check/alert_check.py services/alert-check/
COPY kafka/schemas/ kafka/schemas/

ENV SCHEMA_DIR=/app/kafka/schemas \
    KAFKA_BOOTSTRAP=kafka:29092 \
    METRICS_PORT=8002 \
    PYTHONUNBUFFERED=1

# Prometheus /metrics
EXPOSE 8002
USER nobody
ENTRYPOINT ["python", "services/alert-check/alert_check.py"]
