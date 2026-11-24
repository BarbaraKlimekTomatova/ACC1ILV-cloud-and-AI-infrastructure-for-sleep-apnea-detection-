"""AHI of our system against the clinical AHI, for the 5 demo nights (known limits, doc/model-limits.md).

    python scripts/ahi_vs_clinical.py                 # the 5 demo nights
    python scripts/ahi_vs_clinical.py ucddb010 ...    # other UCDDB nights

Needs data/raw/<night>.npz (in git) and models/model.joblib (services/model-trainer/train.py).
No Kafka, no database: the same feature code and the same models as the live apnea-detector.

Columns
  clinical   scored apnea + hypopnea events (UCDDB, "POSSIBLE" left out) / hours of SLEEP
  labels     minutes labelled as event / hours of RECORDING  = the best a perfect per-minute model can do
  accurate   minutes the accurate model calls apnea or hypopnea / hours of recording (low_carbon)
  fast       minutes the rule rule-v1 calls an event / hours of recording (high_carbon)
"""

import sys
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "common"))
import fast_model as FM  # noqa: E402
import features as F  # noqa: E402

DEMO_NIGHTS = ["ucddb010", "ucddb013", "ucddb017", "ucddb018", "ucddb025"]
SCORED = {"APNEA-O", "APNEA-C", "APNEA-M", "HYP-O", "HYP-C", "HYP-M"}


def severity(ahi):
    return "normal" if ahi < 5 else "mild" if ahi < 15 else "moderate" if ahi < 30 else "severe"


def night_rows(signals):
    """Features of every minute as dicts (for the rule) and as one array (for the model)."""
    nf, rows = F.NightFeatures(), []
    for m in range(len(signals["spo2"]) // 60):
        s1, s4 = slice(m * 60, (m + 1) * 60), slice(m * 240, (m + 1) * 240)
        rows.append(nf.add_minute(signals["spo2"][s1].astype(np.float32),
                                  signals["flow"][s4], signals["thorax"][s4], signals["abdomen"][s4]))
    return rows, np.vstack([F.to_vector(r) for r in rows])


def compare(night, bundle):
    d = np.load(ROOT / "data" / "raw" / f"{night}.npz")
    rows, X = night_rows(d)
    hours = len(rows) / 60
    stage = d["sleep_stage"]
    sleep_hours = ((stage >= 1) & (stage <= 5)).sum() / 60
    classes = [bundle["classes"][int(c)] for c in bundle["model"].classes_]
    accurate = sum(classes[int(np.argmax(p))] != "normal" for p in bundle["model"].predict_proba(X))
    fast = sum(FM.predict(r)[0] != FM.NORMAL for r in rows)
    return {"night": night, "hours": hours, "sleep_hours": sleep_hours,
            "clinical": sum(t in SCORED for t in d["event_type"]) / sleep_hours,
            "labels": (d["apnea"][:len(rows)] == 1).sum() / hours,
            "accurate": accurate / hours, "fast": fast / hours}


def main(nights):
    bundle = joblib.load(ROOT / "models" / "model.joblib")
    print(f"{'night':9} {'rec h':>5} {'sleep h':>7} {'clinical':>8} {'labels':>6} {'accurate':>8} {'fast':>5}   "
          "severity clinical / accurate / fast")
    for n in nights:
        r = compare(n, bundle)
        print(f"{r['night']:9} {r['hours']:5.1f} {r['sleep_hours']:7.1f} {r['clinical']:8.1f} {r['labels']:6.1f} "
              f"{r['accurate']:8.1f} {r['fast']:5.1f}   "
              f"{severity(r['clinical'])} / {severity(r['accurate'])} / {severity(r['fast'])}")


if __name__ == "__main__":
    main(sys.argv[1:] or DEMO_NIGHTS)
