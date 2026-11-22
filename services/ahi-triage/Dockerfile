# ahi-triage (UC2 steps 6-10). Build from the REPO ROOT:
#   docker build -f services/ahi-triage/Dockerfile -t ahi-triage .
# kind: build with the tag ahi-triage:dev, then  kind load docker-image ahi-triage:dev --name apnea  (k8s/README.md)
# Python 3.12 (3.12-3.14 work, see requirements.txt)
FROM python:3.12-slim

WORKDIR /app
COPY services/ahi-triage/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# the service and the message schemas
COPY services/ahi-triage/*.py services/ahi-triage/
COPY kafka/schemas/ kafka/schemas/

ENV KAFKA_BOOTSTRAP=kafka:29092 \
    DATABASE_URL=postgresql://ahi_triage:dev_ahi_triage@postgres:5432/sleep_apnea

# Prometheus /metrics
EXPOSE 8001
USER nobody
ENTRYPOINT ["python", "services/ahi-triage/ahi_triage.py"]
