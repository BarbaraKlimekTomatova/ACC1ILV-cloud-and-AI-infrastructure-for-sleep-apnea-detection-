# Data

Two open PhysioNet datasets. We keep only what a home device measures:
**SpO2, airflow, chest and belly breathing movement**, plus the apnea labels.

| Nights | Dataset | Used for |
|---|---|---|
| `ucddb002` … `ucddb028` (25) | [UCDDB](https://physionet.org/content/ucddb/1.0.0/), scored apnea/hypopnea events | training (20) + live demo (5) |
| `a01r` … `c03r` (8) | [Apnea-ECG](https://physionet.org/content/apnea-ecg/1.0.0/), every minute labelled apnea / normal | held-out test (F1) |

## The steps

Run them in order. Each step reads the folder of the step before.

```bash
pip install -r requirements.txt
python data/01_download.py          # -> data/raw/        (once, ~15 min)
python data/02_clean.py             # -> data/clean/      (a few seconds)
python data/03_to_kafka_messages.py # -> kafka/messages/raw-signals/ (~2 min, 71 MB, not committed)
```

```
PhysioNet ──01_download──> raw/ ──02_clean──> clean/signals/ ──03_to_kafka_messages──> ../kafka/messages/raw-signals/
                                          └─> clean/labels.csv, clean/splits.json        (training only)
```

### Step 1 – `01_download.py` → `data/raw/<night>.npz`

Downloads each night, keeps the 4 signals, lowers the sampling rate
(SpO2 1 Hz, breathing 4 Hz), sets impossible SpO2 (< 50 % or > 100 %) to NaN,
saves one small `.npz` and deletes the big originals (~1.3 GB pass through, 18 MB stay).
Committed to git.

Each `.npz` contains:
- `spo2` 1 Hz in %, NaN = sensor drop-out
- `flow`, `thorax`, `abdomen` 4 Hz, raw device units
- `apnea` one value per minute: 1 apnea/hypopnea, 0 normal, -1 no label
- `sleep_stage` per minute (UCDDB): 0 wake, 1 REM, 2-5 stage 1-4, -1 unknown
- `event_onset_s`, `event_duration_s`, `event_type` scored events (UCDDB)

### Step 2 – `02_clean.py` → `data/clean/`

Small, safe fixes and separating **what the device sends** from **the answers**:

| Output | What it is | In git |
|---|---|---|
| `clean/signals/<night>.npz` | only `spo2`, `flow`, `thorax`, `abdomen`. SpO2 gaps up to 10 s are filled by a straight line; longer gaps stay NaN. | yes |
| `clean/labels.csv` | one row per minute: `night_id, patient_id, source, minute, apnea, event, sleep_stage, usable`. `apnea` = 0/1 (apnea or hypopnea). `event` = 3 classes for UCDDB (`apnea` / `hypopnea` / `normal`, apnea wins if both touch a minute); Apnea-ECG only knows `apnea_or_hypopnea` / `normal`, because its experts did not score the type. `usable = 0` when more than half of the SpO2 is missing or all breathing signals are flat (sensor off). | yes |
| `clean/splits.json` | one entry per night: `split` (train / demo / test), minutes, apnea minutes, AHI. | yes |

Split is **by person**: every UCDDB night is a different person, and the
Apnea-ECG people are never used for training. The 5 demo nights are spread
from mild to severe AHI: ucddb018 (2.2), ucddb017 (12.0), ucddb013 (15.7),
ucddb010 (33.4), ucddb025 (94.1).

No normalisation and no features here: feature engineering lives in the
apnea-detector, so training and live use run the same code.

### Step 3 – `03_to_kafka_messages.py` → `kafka/messages/raw-signals/`

```bash
python data/03_to_kafka_messages.py               # all 33 nights
python data/03_to_kafka_messages.py --split demo  # only the 5 demo nights
python data/03_to_kafka_messages.py ucddb025      # one or more nights by id
```

Writes `kafka/messages/raw-signals/<night_id>.jsonl`: **one line = one minute = one
`raw-signals` message**, valid against
[`raw-signals-value.schema.json`](../kafka/schemas/raw-signals-value.schema.json).
These files are generated, so they are not committed.

| Field | Value |
|---|---|
| `patient_id` | demo nights: `P01` … `P05` (ucddb018, 017, 013, 010, 025, as in `db/init/09_insert_demo_patients.sql`); other nights: their PhysioNet id |
| `minute`, `is_last` | 0, 1, 2 …; `is_last = true` on the last minute only |
| `sent_at` | fixed night start 2026-11-20 22:00 UTC + minute, so the files are reproducible; the device-simulator can put the real time when it replays |
| `spo2` | 60 values (1 Hz), 1 decimal, NaN → `null` |
| `flow`, `thorax`, `abdomen` | 240 values (4 Hz), 3 decimals |

The file also has the builders for the other topics, so every service uses the
same message shape (Aliénor: `raw-signals`, `alerts`, `carbon-signal`; Barbara:
`apnea-events`, `night-results`). Labels never go into a Kafka message.
Tests: `pytest tests/data` checks every builder and one whole night against the schemas.

## Read a night in Python

```python
import csv, numpy as np
sig = np.load("data/clean/signals/ucddb002.npz")
labels = [r for r in csv.DictReader(open("data/clean/labels.csv")) if r["night_id"] == "ucddb002"]
sig["spo2"], labels[:3]
```
