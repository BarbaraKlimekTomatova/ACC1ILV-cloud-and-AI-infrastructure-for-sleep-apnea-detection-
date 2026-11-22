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

**LLM summary (UC2 step 8, [ADR 0009](../../ADR/0009-llm-summary-with-a-local-model.md)):** at the end of a night
a small **local** model (Ollama, `llama3.2:1b`) writes 2 sentences for the doctor (`llm_summary`, `llm_model`).
The prompt has only numbers, no patient id or name, and nothing leaves the machine. The urgency
("review soon" for moderate and severe) is decided in our code, the model only words it.
`llm_gco2` = Ollama's run time × `LLM_WATTS` × the carbon intensity of the night. If Ollama does not
answer, the result is saved and sent without summary (UC2 A4).

```
brew install ollama            # or https://ollama.com/download
ollama serve
ollama pull llama3.2:1b
```

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
`kind load docker-image`. `LLM_URL` in the ConfigMap points to the laptop's Ollama (`host.docker.internal:11434`).
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
| `USE_LLM` | `1` (`0` = no summary) |
| `LLM_URL` / `LLM_MODEL` | `http://localhost:11434` (`http://host.docker.internal:11434` from Docker) / `llama3.2:1b` |
| `LLM_TIMEOUT_S` / `LLM_WATTS` | `60` / `30` (power of the machine running Ollama, for `llm_gco2`) |

## Tests

```
pytest tests/ahi-triage
```

The `results` test runs only with PostgreSQL (`docker compose up -d postgres`) and
`APNEA_TEST_DB=postgresql://apnea_detector:dev_apnea_detector@localhost:5432/sleep_apnea`
(the night row in `raw_nights` is written as `apnea_detector`, the result as `ahi_triage`).
