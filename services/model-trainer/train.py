"""Train the ACCURATE apnea model (UC7, ADR 0005).

    python services/model-trainer/train.py              # train, save, write model_versions
    python services/model-trainer/train.py --no-db      # same, but no database

What it does
  1. Builds the per-minute features of every TRAIN night (data/clean/splits.json)
     with services/common/features.py, the same code the live apnea-detector runs.
  2. Trains a 3-class model: normal / apnea / hypopnea (labels.csv `event`),
     class_weight="balanced" because most minutes are normal.
  3. Tests it on the held-out Apnea-ECG nights (split = test). Their experts did
     not score the type, only "apnea_or_hypopnea" / "normal", so the test is
     binary: the model says apnea OR hypopnea -> 1, normal -> 0. F1, precision
     and recall are for class 1.
  4. Measures the energy and CO2 of the training with CodeCarbon.
  5. Saves models/model.joblib (not in git) and inserts one row into
     model_versions as DB user model_trainer, status = 'pending'
     (the F1 gate in CI/CD decides approved / rejected).

The saved file is a dict:
    {"model": classifier, "features": FEATURES, "classes": [...], "version": ..., "metrics": {...}}
so the detector can check the feature order before it predicts.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import classification_report, f1_score, precision_score, recall_score

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "common"))
import features as F  # noqa: E402

CLASSES = ["normal", "apnea", "hypopnea"]          # model output, index = class id
MODEL = "accurate"
DEFAULT_DATA = ROOT / "data" / "clean"
DEFAULT_OUT = ROOT / "models" / "model.joblib"
DEFAULT_DB = "postgresql://model_trainer:dev_model_trainer@localhost:5432/sleep_apnea"
# model_versions.region -> CodeCarbon country code (grid CO2 intensity)
REGION_ISO = {"AT": "AUT", "NO": "NOR", "PL": "POL"}

# label in labels.csv -> class id. Test nights only know apnea_or_hypopnea (-> 1 = "some event").
TRAIN_LABEL = {"normal": 0, "apnea": 1, "hypopnea": 2}
TEST_LABEL = {"normal": 0, "apnea_or_hypopnea": 1, "apnea": 1, "hypopnea": 1}


# ------------------------------------------------------------------ data
def load_splits(data_dir):
    with open(Path(data_dir) / "splits.json") as f:
        return {n["night_id"]: n["split"] for n in json.load(f)}


def load_labels(data_dir):
    """night_id -> {minute: (event, usable)}"""
    labels = {}
    with open(Path(data_dir) / "labels.csv", newline="") as f:
        for r in csv.DictReader(f):
            labels.setdefault(r["night_id"], {})[int(r["minute"])] = (r["event"], r["usable"] == "1")
    return labels


def night_xy(data_dir, night_id, minute_labels, mapping):
    """Features of ALL minutes (causal, like live), then keep the labelled, usable ones."""
    sig = np.load(Path(data_dir) / "signals" / f"{night_id}.npz")
    X = F.night_features(sig)
    keep, y = [], []
    for m in range(len(X)):
        event, usable = minute_labels.get(m, ("unknown", False))
        if usable and event in mapping:
            keep.append(m)
            y.append(mapping[event])
    return X[keep], np.array(y, dtype=np.int64)


def build_set(data_dir, nights, labels, mapping):
    Xs, ys = [], []
    for n in nights:
        X, y = night_xy(data_dir, n, labels.get(n, {}), mapping)
        Xs.append(X)
        ys.append(y)
    if not Xs:
        return np.empty((0, len(F.FEATURES)), np.float32), np.empty(0, np.int64)
    return np.vstack(Xs), np.concatenate(ys)


# ------------------------------------------------------------------ model
def make_model(seed=0):
    """Gradient-boosted trees: on our data a bit better than a random forest
    (held-out F1 0.91 vs 0.89) and faster to train."""
    return HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.05, class_weight="balanced", random_state=seed)


def evaluate(model, X, y_binary):
    """3-class prediction -> binary (apnea or hypopnea = 1), scores for class 1."""
    pred = (model.predict(X) != TRAIN_LABEL["normal"]).astype(int)
    kw = dict(zero_division=0)
    return {
        "f1": float(f1_score(y_binary, pred, **kw)),
        "precision": float(precision_score(y_binary, pred, **kw)),
        "recall": float(recall_score(y_binary, pred, **kw)),
        "test_minutes": int(len(y_binary)),
    }


# ------------------------------------------------------------------ CO2
class Carbon:
    """CodeCarbon around the training. Offline = no internet needed, the grid
    intensity comes from the country of the region. If it fails: None, not a crash."""

    def __init__(self, region, enabled=True):
        self.region, self.enabled, self.tracker = region, enabled, None
        self.kwh = self.gco2 = None

    def __enter__(self):
        if self.enabled:
            try:
                from codecarbon import OfflineEmissionsTracker
                self.tracker = OfflineEmissionsTracker(
                    country_iso_code=REGION_ISO[self.region], project_name="model-trainer",
                    save_to_file=False, log_level="error")
                self.tracker.start()
            except Exception as e:  # noqa: BLE001
                print(f"CodeCarbon not available ({e}), kwh/gco2 stay empty")
                self.tracker = None
        return self

    def __exit__(self, *exc):
        if self.tracker is not None:
            kg = self.tracker.stop()
            data = self.tracker.final_emissions_data
            self.kwh = float(data.energy_consumed) if data else None
            self.gco2 = float(kg) * 1000 if kg is not None else None
        return False


# ------------------------------------------------------------------ database
def next_version(conn):
    """accurate-v1, accurate-v2, ... (model_trainer may read model_versions)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT version FROM model_versions WHERE model = %s AND version LIKE %s",
            (MODEL, f"{MODEL}-v%"))
        nums = [int(v[len(MODEL) + 2:]) for (v,) in cur.fetchall() if v[len(MODEL) + 2:].isdigit()]
    return f"{MODEL}-v{max(nums, default=0) + 1}"


def version_row(version, train_nights, triggered_by, metrics, kwh, gco2, region, artifact_path,
                doctor_corrections_used=0):
    """One model_versions row (db/init/04_model_versions.sql)."""
    return {
        "version": version,
        "model": MODEL,
        "trained_at": datetime.now(timezone.utc),
        "train_nights": train_nights,
        "doctor_corrections_used": doctor_corrections_used,
        "triggered_by": triggered_by,
        "f1": metrics["f1"],
        "precision_score": metrics["precision"],
        "recall_score": metrics["recall"],
        "kwh": kwh,
        "gco2": gco2,
        "region": region,
        "status": "pending",
        "artifact_path": artifact_path,
    }


def insert_version(conn, row):
    cols = list(row)
    sql = (f"INSERT INTO model_versions ({', '.join(cols)}) "
           f"VALUES ({', '.join(['%s'] * len(cols))})")
    with conn.cursor() as cur:
        cur.execute(sql, [row[c] for c in cols])
    conn.commit()


# ------------------------------------------------------------------ main
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Train the accurate apnea model.")
    p.add_argument("--data-dir", default=str(DEFAULT_DATA))
    p.add_argument("--out", default=os.environ.get("MODEL_PATH", str(DEFAULT_OUT)))
    p.add_argument("--db-url", default=os.environ.get("DATABASE_URL", DEFAULT_DB))
    p.add_argument("--no-db", action="store_true", help="do not write model_versions")
    p.add_argument("--no-carbon", action="store_true", help="skip CodeCarbon (tests)")
    p.add_argument("--region", default=os.environ.get("REGION", "AT"), choices=sorted(REGION_ISO))
    p.add_argument("--triggered-by", default=os.environ.get("TRIGGERED_BY", "manual"),
                   choices=["schedule", "manual", "drift"])
    p.add_argument("--version", help="override the version name (default: next accurate-vN)")
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    splits = load_splits(a.data_dir)
    labels = load_labels(a.data_dir)
    train = sorted(n for n, s in splits.items() if s == "train")
    test = sorted(n for n, s in splits.items() if s == "test")
    print(f"train nights: {len(train)}   test nights: {len(test)}")

    conn = None
    if not a.no_db:
        import psycopg
        conn = psycopg.connect(a.db_url)
    version = a.version or (next_version(conn) if conn else f"{MODEL}-dev")

    t0 = time.time()
    with Carbon(a.region, enabled=not a.no_carbon) as co2:
        X_train, y_train = build_set(a.data_dir, train, labels, TRAIN_LABEL)
        model = make_model(a.seed).fit(X_train, y_train)
    counts = np.bincount(y_train, minlength=len(CLASSES))
    print(f"trained on {len(y_train)} minutes "
          f"({', '.join(f'{c} {n}' for c, n in zip(CLASSES, counts))}) in {time.time() - t0:.0f} s")

    X_test, y_test = build_set(a.data_dir, test, labels, TEST_LABEL)
    metrics = evaluate(model, X_test, y_test)
    print(f"held-out Apnea-ECG ({metrics['test_minutes']} min): F1 {metrics['f1']:.3f}  "
          f"precision {metrics['precision']:.3f}  recall {metrics['recall']:.3f}")
    demo = sorted(n for n, s in splits.items() if s == "demo")
    X_demo, y_demo = build_set(a.data_dir, demo, labels, TRAIN_LABEL)
    if len(y_demo):                     # info only: 3 classes on the UCDDB demo nights
        print("3 classes on the demo nights (info, not stored):")
        print(classification_report(y_demo, model.predict(X_demo), labels=range(len(CLASSES)),
                                    target_names=CLASSES, zero_division=0))
    print(f"training energy: {co2.kwh} kWh, {co2.gco2} gCO2 (region {a.region})")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": F.FEATURES, "classes": CLASSES,
                 "version": version, "metrics": metrics}, out)
    print(f"saved {out}  version {version}")

    artifact = out.resolve()
    artifact = artifact.relative_to(ROOT) if artifact.is_relative_to(ROOT) else artifact
    row = version_row(version, len(train), a.triggered_by, metrics, co2.kwh, co2.gco2,
                      a.region, str(artifact))
    if conn:
        insert_version(conn, row)
        conn.close()
        print(f"model_versions: inserted {version} (status pending)")
    return row


if __name__ == "__main__":
    main()
