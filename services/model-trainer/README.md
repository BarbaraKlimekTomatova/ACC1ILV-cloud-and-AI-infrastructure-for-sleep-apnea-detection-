# model-trainer

UC7 ([Retrain model](../../diagrams/sequences/10.11_B_UC7-retrain-model_v1.md)),
[ADR 0005](../../ADR/0005-model-lifecycle-carbon-aware-retraining.md). Owner: Barbara.
Runs as a Kubernetes Job, not as a long-running service.

```
data/clean/ ──► train.py ──► models/model.joblib + model_versions (status pending)
                                   │
                                   ▼
                               gate.py ──► approved (F1 ≥ 0.80) / rejected
```

- **`train.py`** builds the per-minute features with `services/common/features.py` (the same
  code the live `apnea-detector` runs), trains the `accurate` model (or `--model fast`),
  tests it on the held-out Apnea-ECG nights (F1, precision, recall), measures `kwh` and `gco2`
  with CodeCarbon and saves `models/model.joblib` (not in git). With the database it also
  inserts one `model_versions` row with `status = pending` (DB user `model_trainer`).
- **`gate.py`** is the F1 gate (UC7 steps 6–7, A1). A version is approved only if its F1 is
  at least the threshold (default `0.80`, `F1_THRESHOLD`) and not worse than the version in use.
- **`carbon_wait.py`** (skeleton, not used yet) will wait for `low_carbon` before training
  (UC7 step 2, A2).

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
| `MODEL` | `accurate` (`fast` = the cheap model, ADR 0003) |
| `MODEL_PATH` | `models/model.joblib` (`models/model-fast.joblib` for `fast`) |
| `REGION` | `AT` (CodeCarbon grid: `AT`, `NO`, `PL`) |
| `TRIGGERED_BY` | `manual` (`schedule`, `drift`) |
| `F1_THRESHOLD` | `0.80` |

## Tests

```
pytest tests/model-trainer
```

They use a tiny fake `data/clean/` folder, so they need no database and no CodeCarbon.
