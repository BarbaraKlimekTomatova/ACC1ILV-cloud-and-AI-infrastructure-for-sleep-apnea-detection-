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
python data/03_to_kafka_messages.py # -> data/kafka_messages/   (not done yet)
```

```
PhysioNet ──01_download──> raw/ ──02_clean──> clean/signals/ ──03_to_kafka_messages──> kafka_messages/  (topic raw-signals)
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
| `clean/labels.csv` | one row per minute: `night_id, patient_id, source, minute, apnea, sleep_stage, usable`. `usable = 0` when more than half of the SpO2 is missing or all breathing signals are flat (sensor off). | yes |
| `clean/splits.json` | one entry per night: `split` (train / demo / test), minutes, apnea minutes, AHI. | yes |

Split is **by person**: every UCDDB night is a different person, and the
Apnea-ECG people are never used for training. The 5 demo nights are spread
from mild to severe AHI: ucddb018 (2.2), ucddb017 (12.0), ucddb013 (15.7),
ucddb010 (33.4), ucddb025 (94.1).

No normalisation and no features here: feature engineering lives in the
apnea-detector, so training and live use run the same code.

### Step 3 – `03_to_kafka_messages.py` → `data/kafka_messages/` (not done yet)

Only a skeleton with one method per Kafka topic and a TODO for who builds it
(Aliénor: `raw-signals`, `alerts`, `carbon-signal`; Barbara: `apnea-events`,
`night-results`). The message format will be described here when it is done.
Labels never go into a Kafka message.

## Read a night in Python

```python
import csv, numpy as np
sig = np.load("data/clean/signals/ucddb002.npz")
labels = [r for r in csv.DictReader(open("data/clean/labels.csv")) if r["night_id"] == "ucddb002"]
sig["spo2"], labels[:3]
```
