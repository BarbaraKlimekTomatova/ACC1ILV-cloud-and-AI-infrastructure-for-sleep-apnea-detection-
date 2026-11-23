# carbon-scheduler (UC5). Build from the REPO ROOT:
#   docker build -f services/carbon-scheduler/Dockerfile -t carbon-scheduler .
FROM python:3.12-slim

WORKDIR /app
COPY services/carbon-scheduler/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/carbon-scheduler/ services/carbon-scheduler/
COPY kafka/schemas/ kafka/schemas/

ENV SCHEMA_DIR=/app/kafka/schemas \
    KAFKA_BOOTSTRAP=kafka:29092 \
    DATABASE_URL=postgresql://carbon_scheduler:dev_carbon_scheduler@postgres:5432/sleep_apnea \
    METRICS_PORT=8004 \
    PYTHONUNBUFFERED=1

# Prometheus /metrics
EXPOSE 8004
USER nobody
ENTRYPOINT ["python", "services/carbon-scheduler/carbon_scheduler.py"]
