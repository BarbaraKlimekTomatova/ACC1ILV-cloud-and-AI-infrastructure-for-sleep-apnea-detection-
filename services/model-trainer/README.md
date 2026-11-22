# model-trainer

UC7 ([Retrain model](../../diagrams/sequences/10.11_B_UC7-retrain-model_v1.md)),
[ADR 0005](../../ADR/0005-model-lifecycle-carbon-aware-retraining.md). Owner: Barbara.
Runs as a Kubernetes CronJob (Sunday 02:00), not as a long-running service.

```
data/clean/ ──► train.py ──► models/model.joblib + model_versions (status pending)
                                   │
                                   ▼
                               gate.py ──► approved (F1 ≥ 0.80) / rejected
```

- **`train.py`** builds the per-minute features with `services/common/features.py` (the same
  code the live `apnea-detector` runs), trains the `accurate` model (the fast model is a rule, `services/common/fast_model.py`),
  tests it on the held-out Apnea-ECG nights (F1, precision, recall), measures `kwh` and `gco2`
  with CodeCarbon and saves `models/model.joblib` (not in git). With the database it also
  inserts one `model_versions` row with `status = pending` (DB user `model_trainer`).
- **`gate.py`** is the F1 gate (UC7 steps 6–7, A1). A version is approved only if its F1 is
  at least the threshold (default `0.80`, `F1_THRESHOLD`) and not worse than the version in use.
- **`carbon_wait.py`** waits for `low_carbon` on the Kafka topic `carbon-signal` before training
  (UC7 step 2). It starts at the newest message (= the mode right now) and listens for new ones.
  No `low_carbon` within `MAX_WAIT_S` → no training, no `model_versions` row, exit 0 (A2).
  The region of the `low_carbon` message is stored as `model_versions.region`.

### Try the low-carbon wait by hand

Needs only Kafka (`docker compose up -d`), not the carbon-scheduler:

```
python services/model-trainer/train.py --wait-low-carbon --no-db --max-wait-s 300
docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:29092 --topic carbon-signal <<< '{"region":"PL","carbon_intensity":650,"mode":"high_carbon","sent_at":"2026-11-23T02:00:00+00:00"}'
docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:29092 --topic carbon-signal <<< '{"region":"NO","carbon_intensity":30,"mode":"low_carbon","sent_at":"2026-11-23T03:00:00+00:00"}'
```

The trainer logs `high_carbon in PL (650 gCO2/kWh), waiting ...`, then `low_carbon in NO`, and trains.

**Python 3.12, 3.13 or 3.14** (Docker and CI use 3.12; numpy 2.5 needs 3.12+).

## Run locally

```
pip install -r services/model-trainer/requirements.txt
python services/model-trainer/train.py --no-db --no-carbon
python services/model-trainer/gate.py --model-file models/model.joblib
```

With the docker-compose PostgreSQL (`docker compose up -d postgres`), leave out `--no-db`
and run `gate.py` without `--model-file`: it then checks the newest `pending` row and sets
it to `approved` or `rejected`.

## Docker

Build from the repo root:

```
docker build -f services/model-trainer/Dockerfile -t model-trainer .
docker run --rm -v "$PWD/models:/app/models" model-trainer --no-db
docker run --rm -v "$PWD/models:/app/models" --entrypoint python model-trainer services/model-trainer/gate.py --model-file models/model.joblib
```

## Kubernetes (kind)

[`k8s/model-trainer.yaml`](../../k8s/model-trainer.yaml): CronJob every Sunday 02:00 Europe/Vienna
(`TRIGGERED_BY=schedule`), never two trainings at once, 1 retry. The trained files go to the
PersistentVolumeClaim `models`. Image `model-trainer:dev`, loaded with `kind load docker-image`.
Start a training by hand:

```
kubectl create job --from=cronjob/model-trainer model-trainer-manual
kubectl logs -f job/model-trainer-manual
```

Start the cluster and deploy: [k8s/README.md](../../k8s/README.md).

## CI (`.github/workflows/model-trainer.yml`)

Runs on a change in `services/model-trainer/`, `services/common/`, `tests/model-trainer/` or
`data/clean/`, or by hand (Actions → model-trainer → Run workflow, with an optional F1 threshold).

1. **test**: `pytest tests/model-trainer`.
2. **f1-gate** (after test): trains on `data/clean/` without database and CodeCarbon, then
   `gate.py --model-file models/model.joblib`. F1 below the threshold → the job fails (red).
   The model is uploaded as a build artifact and the F1 is written to the run summary.

Building and pushing the image after an approved gate (CD) is not part of the workflow yet.

## Gate exit codes

| Code | Meaning |
|---|---|
| `0` | approved |
| `1` | rejected (F1 below the threshold or worse than the model in use) |
| `2` | nothing to check (no `pending` version in the database) |

In GitHub Actions `gate.py` also writes `status`, `version` and `f1` to `$GITHUB_OUTPUT`.

## Settings (environment variables)

| Variable | Default |
|---|---|
| `DATABASE_URL` | `postgresql://model_trainer:dev_model_trainer@localhost:5432/sleep_apnea` |
| `MODEL_PATH` | `models/model.joblib` |
| `REGION` | `AT` (CodeCarbon grid: `AT`, `NO`, `PL`) |
| `TRIGGERED_BY` | `manual` (`schedule`, `drift`) |
| `F1_THRESHOLD` | `0.80` |
| `WAIT_LOW_CARBON` / `MAX_WAIT_S` | off (`1` in the CronJob) / `21600` (6 h) |
| `KAFKA_BOOTSTRAP` | `localhost:9092` (`kafka:29092` in Docker and Kubernetes) |

## Tests

```
pytest tests/model-trainer
```

They use a tiny fake `data/clean/` folder, so they need no database and no CodeCarbon.
