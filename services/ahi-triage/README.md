# ahi-triage

UC2 steps 6–10. Owner: Barbara. Everything is in `ahi_triage.py`, start with
`python services/ahi-triage/ahi_triage.py`.

```
apnea-events ──► ahi-triage ──► results (PostgreSQL) ──► night-results ──► doctor-dashboard
 (one per minute)   counts the night, at is_last: AHI + severity
```

1. Reads `apnea-events` (consumer group `ahi-triage`) and counts the events of each night.
   Every `(night_id, minute)` is counted once, because Kafka can deliver a message twice.
2. At the last minute (`is_last`):
   - **AHI** = minutes with an event (`apnea`, `hypopnea`, `apnea_or_hypopnea`) / hours of recording
   - **severity**: normal < 5 · mild 5–15 · moderate 15–30 · severe ≥ 30
   - **deadline_met**: finished before 08:00 (Europe/Vienna); `DEMO_TIME` works like in the detector
   - `model`, `model_version`, `carbon_mode`, `region`, `kwh`, `gco2` from the last message
3. Saves one row in `results` (DB user `ahi_triage`) and sends `night-results`.

**Simplification:** the detector gives one event per minute, not every single apnea, and we
only know the length of the recording, not the hours of sleep. So our AHI is "minutes with an
event per hour of recording". With many apneas in one minute (severe cases) it is lower than a
clinical AHI.

**Restart during a night (UC2 A3):** the counts are in memory, so the Kafka offset only moves
past a message when its night is saved in `results`. After a restart the unfinished nights are
read again; a night that is already in `results` is not saved or sent twice.

**TODO (UC2 step 8):** short LLM summary for the doctor (`llm_summary`, `llm_model`,
`llm_gco2`). Until then these columns stay empty (UC2 A4: the result is saved without summary).

**Python 3.12, 3.13 or 3.14** (Docker and CI use 3.12); not 3.15 (no confluent-kafka wheel yet).

## Run

```
docker compose up -d
docker compose --profile triage up --build ahi-triage
```

or without Docker: `pip install -r services/ahi-triage/requirements.txt && python services/ahi-triage/ahi_triage.py`

## Kubernetes (kind)

[`k8s/ahi-triage.yaml`](../../k8s/ahi-triage.yaml): Deployment with exactly 1 pod (the open nights are in
memory, so it does not scale out) and a Service for `/metrics`. Image `ahi-triage:dev`, loaded with
`kind load docker-image`. The Secret `llm-api` is already mounted as `LLM_API_KEY` for the LLM summary.
Start the cluster and deploy: [k8s/README.md](../../k8s/README.md).

## Settings (environment variables)

| Variable | Default |
|---|---|
| `KAFKA_BOOTSTRAP` | `localhost:9092` (`kafka:29092` in Docker and Kubernetes) |
| `DATABASE_URL` | `postgresql://ahi_triage:dev_ahi_triage@localhost:5432/sleep_apnea` |
| `USE_DB` | `1` (`0` = no `results`) |
| `DEADLINE` / `TZ_DEADLINE` | `08:00` / `Europe/Vienna` |
| `DEMO_TIME` | empty = real time |
| `METRICS_PORT` | `8001` (Prometheus `/metrics`; the detector uses 8000) |

## Tests

```
pytest tests/ahi-triage
```

The `results` test runs only with PostgreSQL (`docker compose up -d postgres`) and
`APNEA_TEST_DB=postgresql://apnea_detector:dev_apnea_detector@localhost:5432/sleep_apnea`
(the night row in `raw_nights` is written as `apnea_detector`, the result as `ahi_triage`).
