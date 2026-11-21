# apnea-detector

UC2 (screen night), UC3 (alert check) and UC5 (carbon-aware). Owner: Barbara; the alert check (UC3) is Aliénor's.

Everything is in `detector.py`, start with `python services/apnea-detector/detector.py`:

1. the logic (alert check, carbon rule, demo clock, models, analysis), no Kafka and no database,
   so the tests run without them
2. Kafka (three loops), the table `raw_nights`, Prometheus metrics and the start

**Python 3.12, 3.13 or 3.14** (Docker and CI use 3.12). Not 3.11 (numpy 2.5 needs 3.12+) and not
3.15 (confluent-kafka has no wheel for it yet).

## How it works

| Loop | Consumer group | Paused? | Does |
|---|---|---|---|
| alerts | `apnea-alerts` | never (ADR 0002) | creates the `raw_nights` row at minute 0, SpO₂ < 80 % → `alerts`, saves every minute |
| carbon | – | – | reads the newest `carbon-signal` |
| analysis | `apnea-detector` | yes (ADR 0003) | `NightFeatures` + model → one `apnea-events` per minute |

| carbon mode | time (Europe/Vienna) | analysis | `event` |
|---|---|---|---|
| `low_carbon` | any | accurate model | apnea / hypopnea / normal |
| `high_carbon` | more than 2 h before 08:00 | pause, minutes wait in Kafka | – |
| `high_carbon` | 2 h or less before 08:00 | fast model | apnea_or_hypopnea / normal |

- `kwh` / `gco2` are only on the last minute, for the whole night: CPU seconds × `CPU_WATTS`,
  CO₂ with the `carbon_intensity` of `carbon-signal` (CodeCarbon cannot measure steps of milliseconds).
- Kafka delivers at least once: a minute that was already analysed or saved is skipped.
  ahi-triage should also count each `(night_id, minute)` only once.
- A pod that starts in the middle of a night begins with an empty history; after 5 minutes the
  baselines are normal again.

## Demo

- **Clock:** `DEMO_TIME=23:00` (night: `high_carbon` → pause) or `DEMO_TIME=06:30`
  (morning: `high_carbon` → fast model). The clock runs on from that time. Restart the detector after a change.
- **Carbon mode:** send `low_carbon` / `high_carbon` to the `carbon-signal` topic, no restart needed.

## Run locally

```
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r services/apnea-detector/requirements.txt pytest==8.3.4
docker compose up -d
python services/model-trainer/train.py --no-db
python services/model-trainer/train.py --no-db --model fast
python services/apnea-detector/detector.py
```

Docker: `docker compose --profile detector up --build apnea-detector`.

## Settings (environment variables)

| Variable | Default |
|---|---|
| `KAFKA_BOOTSTRAP` | `localhost:9092` (`kafka:29092` inside Docker) |
| `DATABASE_URL` | `postgresql://apnea_detector:dev_apnea_detector@localhost:5432/sleep_apnea` |
| `USE_DB` | `1` (`0` = no `raw_nights`) |
| `MODEL_PATH` / `MODEL_FAST_PATH` | `models/model.joblib` / `models/model-fast.joblib` (no fast file → accurate) |
| `DEFAULT_CARBON_MODE` / `DEFAULT_CARBON_INTENSITY` | `low_carbon` / `300`, until the first `carbon-signal` |
| `DEMO_TIME` | empty = real time |
| `DEADLINE` / `DEADLINE_MARGIN_MIN` / `TZ_DEADLINE` | `08:00` / `120` / `Europe/Vienna` |
| `REGION` | region of the node (AT / NO / PL); empty = region of `carbon-signal` |
| `ALERT_THRESHOLD` / `MIN_VALID_SPO2` | `80` / `50` (lower = sensor artefact) |
| `CPU_WATTS` | `15` |
| `METRICS_PORT` | `8000` (Prometheus `/metrics`) |

## Tests

```
pytest tests/common tests/apnea-detector
```

The `raw_nights` test runs only with PostgreSQL (`docker compose up -d postgres`) and
`APNEA_TEST_DB=postgresql://apnea_detector:dev_apnea_detector@localhost:5432/sleep_apnea`.
