"""Tests for services/model-trainer/train.py:  pytest  (settings in pytest.ini)

A tiny fake data/clean/ folder (4 short nights) so the tests run in seconds
and need no database and no CodeCarbon.
"""

import csv
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "model-trainer"))
import features as F  # noqa: E402
import train as T  # noqa: E402

MINUTES = 12


def fake_night(events):
    """Normal breathing; 'apnea' minutes have no airflow, 'hypopnea' half airflow + desaturation."""
    t = np.arange(MINUTES * 240) / 4
    wave = np.sin(2 * np.pi * 0.25 * t).astype(np.float32)
    flow, thorax, abdomen = wave.copy(), wave.copy(), wave.copy()
    spo2 = np.full(MINUTES * 60, 96.0, np.float32)
    for m, e in enumerate(events):
        b = slice(m * 240, (m + 1) * 240)
        if e in ("apnea", "apnea_or_hypopnea"):
            flow[b] = 0.0
            spo2[m * 60 + 30: (m + 1) * 60] = 90.0
        elif e == "hypopnea":
            flow[b] *= 0.4
            spo2[m * 60 + 30: (m + 1) * 60] = 92.0
    return {"spo2": spo2, "flow": flow, "thorax": thorax, "abdomen": abdomen}


@pytest.fixture
def data_dir(tmp_path):
    pattern = ["normal"] * 4 + ["apnea", "normal", "hypopnea", "normal"] * 2
    nights = {  # night_id: (split, source, events)
        "ucddb901": ("train", "ucddb", pattern),
        "ucddb902": ("train", "ucddb", pattern[::-1]),
        "ucddb903": ("demo", "ucddb", pattern),
        "x01r": ("test", "apnea-ecg",
                 [e if e == "normal" else "apnea_or_hypopnea" for e in pattern]),
    }
    (tmp_path / "signals").mkdir()
    rows, splits = [], []
    for n, (split, source, events) in nights.items():
        np.savez(tmp_path / "signals" / f"{n}.npz", **fake_night(events))
        for m, e in enumerate(events):
            rows.append([n, n, source, m, int(e != "normal"), e, -1, 1])
        splits.append({"night_id": n, "split": split, "minutes": MINUTES})
    rows[0][-1] = 0                                   # one unusable minute
    with open(tmp_path / "labels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["night_id", "patient_id", "source", "minute", "apnea", "event",
                    "sleep_stage", "usable"])
        w.writerows(rows)
    (tmp_path / "splits.json").write_text(json.dumps(splits))
    return tmp_path


def test_night_xy_keeps_only_usable_labelled_minutes(data_dir):
    labels = T.load_labels(data_dir)
    X, y = T.night_xy(data_dir, "ucddb901", labels["ucddb901"], T.TRAIN_LABEL)
    assert X.shape == (MINUTES - 1, len(F.FEATURES))  # minute 0 is unusable
    assert set(y) == {0, 1, 2}


def test_test_nights_are_binary(data_dir):
    labels = T.load_labels(data_dir)
    _, y = T.night_xy(data_dir, "x01r", labels["x01r"], T.TEST_LABEL)
    assert set(y) == {0, 1}


def test_evaluate_counts_hypopnea_as_event():
    class Fixed:
        def predict(self, X):
            return np.array([0, 1, 2, 2])
    m = T.evaluate(Fixed(), np.zeros((4, 1)), np.array([0, 1, 1, 0]))
    assert m["recall"] == 1.0 and m["precision"] == pytest.approx(2 / 3)


def test_main_trains_and_saves_without_db(data_dir, tmp_path):
    out = tmp_path / "models" / "model.joblib"
    row = T.main(["--data-dir", str(data_dir), "--out", str(out), "--no-db", "--no-carbon"])
    bundle = joblib.load(out)
    assert bundle["features"] == F.FEATURES and bundle["classes"] == T.CLASSES
    assert bundle["model"].predict(np.zeros((1, len(F.FEATURES)))).shape == (1,)
    assert row["model"] == "accurate" and row["status"] == "pending"
    assert row["train_nights"] == 2
    for k in ("f1", "precision_score", "recall_score"):
        assert 0 <= row[k] <= 1


def test_version_row_matches_table_columns():
    cols = ["version", "model", "trained_at", "train_nights", "doctor_corrections_used",
            "triggered_by", "f1", "precision_score", "recall_score", "kwh", "gco2",
            "region", "status", "artifact_path"]
    row = T.version_row("accurate-v1", 20, "manual", {"f1": .9, "precision": .8, "recall": 1.},
                        0.001, 0.1, "AT", "models/model.joblib")
    assert list(row) == cols


class FakeConn:
    def __init__(self, versions):
        self.versions, self.executed, self.committed = versions, [], False

    def cursor(self):
        conn = self

        class Cur:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def execute(self, sql, params): conn.executed.append((sql, params))
            def fetchall(self): return [(v,) for v in conn.versions]
        return Cur()

    def commit(self):
        self.committed = True


def test_next_version_counts_up():
    assert T.next_version(FakeConn([])) == "accurate-v1"
    assert T.next_version(FakeConn(["accurate-v1", "accurate-v3", "accurate-dev"])) == "accurate-v4"


def test_insert_version_writes_one_row():
    conn = FakeConn([])
    row = T.version_row("accurate-v1", 20, "manual", {"f1": .9, "precision": .8, "recall": 1.},
                        None, None, "AT", "models/model.joblib")
    T.insert_version(conn, row)
    sql, params = conn.executed[0]
    assert sql.startswith("INSERT INTO model_versions (version, model,")
    assert len(params) == 14 and conn.committed
