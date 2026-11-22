"""apnea-detector tests in one file: alert check, carbon rule with the demo clock, analysis,
the alert loop, and raw_nights with a real PostgreSQL (optional). No Kafka needed."""

import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from jsonschema import Draft202012Validator
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "apnea-detector"))
sys.path.insert(0, str(ROOT / "services" / "common"))

import detector as D  # noqa: E402
import features as F  # noqa: E402


# ---------------------------------------------------------------- helpers: fake model, fake nights
def fake_bundle(version="test"):
    """A real sklearn model with the real FEATURES, trained on random rows."""
    X = np.random.default_rng(0).normal(size=(90, len(F.FEATURES)))
    return {"model": LogisticRegression(max_iter=500).fit(X, np.repeat([0, 1, 2], 30)),
            "features": list(F.FEATURES), "classes": ["normal", "apnea", "hypopnea"],
            "version": version, "metrics": {}}


def raw_minute(minute, is_last=False, spo2=96.0, amp=1.0, night_id="ucddb013", patient_id="P03",
               seconds=60):
    t = (np.arange(240) / 4)[: seconds * 4]
    br = (amp * np.sin(2 * np.pi * 0.25 * t)).round(3).tolist()
    return {"patient_id": patient_id, "night_id": night_id, "source": "ucddb",
            "minute": minute, "is_last": is_last, "sent_at": "2026-11-20T22:08:00+00:00",
            "spo2": [spo2] * seconds, "flow": br, "thorax": br, "abdomen": br}


def raw_night(minutes=12, apnea_at=(6, 7)):
    return [raw_minute(m, is_last=m == minutes - 1, spo2=88.0 if m in apnea_at else 96.0,
                       amp=0.05 if m in apnea_at else 1.0) for m in range(minutes)]


@pytest.fixture
def errors():
    """errors(topic, message) -> list of schema errors (empty = valid)."""
    def check(topic, message):
        schema = json.loads((ROOT / "kafka" / "schemas" / f"{topic}-value.schema.json").read_text())
        return [e.message for e in Draft202012Validator(schema).iter_errors(message)]
    return check


@pytest.fixture
def analyzer():
    return D.Analyzer(D.Model(fake_bundle("accurate-test"), D.ACCURATE),
                      D.Model(fake_bundle("fast-test"), D.FAST))


VIE = ZoneInfo("Europe/Vienna")
LOW = {"mode": "low_carbon", "carbon_intensity": 35.0, "region": "NO"}
HIGH = {"mode": "high_carbon", "carbon_intensity": 420.0, "region": "PL"}


def at(h, m=0):
    return datetime(2026, 11, 21, h, m, tzinfo=VIE)


# ---------------------------------------------------------------- alert check
def test_alert_below_80(errors):
    raw = raw_minute(8, spo2=95.0, patient_id="P05", night_id="ucddb025")
    raw["spo2"][10] = 76.0
    alert = D.alert_for(raw)
    assert alert["spo2_min"] == 76.0 and alert["minute"] == 8
    assert errors("alerts", alert) == []


def test_no_alert_at_80_or_for_dropouts_and_artefacts():
    assert D.alert_for(raw_minute(3, spo2=80.0)) is None
    raw = raw_minute(3, spo2=95.0)
    raw["spo2"][0], raw["spo2"][1] = None, 0.0          # drop-out, finger clip off
    assert D.alert_for(raw) is None


# ---------------------------------------------------------------- carbon rule
def test_low_carbon_always_accurate():
    assert D.decide("low_carbon", at(23)) == D.ACCURATE


def test_high_carbon_pause_at_night_fast_in_the_morning():
    assert D.decide("high_carbon", at(23)) == D.PAUSE
    assert D.decide("high_carbon", at(5, 59)) == D.PAUSE
    assert D.decide("high_carbon", at(6, 0)) == D.FAST
    assert D.decide("high_carbon", at(7, 55)) == D.FAST


def test_high_carbon_after_the_deadline_finishes_late_nights_now():
    assert D.decide("high_carbon", at(8, 30)) == D.FAST         # late night: do not wait for tomorrow
    assert D.decide("high_carbon", at(19, 59)) == D.FAST
    assert D.decide("high_carbon", at(20, 0)) == D.PAUSE        # new night: 08:00 tomorrow is far


def test_demo_clock():
    clock = D.Clock("06:30")
    now = clock.now()
    assert (now.hour, now.minute) == (6, 30)
    assert D.decide("high_carbon", now) == D.FAST
    assert D.decide("high_carbon", D.Clock("23:00").now()) == D.PAUSE
    real = D.Clock(None).now()
    assert abs(real - datetime.now(VIE)) < timedelta(seconds=1)


# ---------------------------------------------------------------- analysis
def test_one_valid_message_per_minute(analyzer, errors):
    out = [analyzer.process(r, D.ACCURATE, LOW) for r in raw_night(12)]
    assert [m["minute"] for m in out] == list(range(12))
    assert all(errors("apnea-events", m) == [] for m in out)
    assert {m["event"] for m in out} <= {"normal", "apnea", "hypopnea"}
    assert out[0]["model"] == "accurate" and out[0]["region"] == "NO"
    assert "kwh" not in out[0]                                  # energy only on the last minute
    assert out[-1]["kwh"] > 0 and out[-1]["gco2"] > 0
    assert analyzer.nights == {}                                # finished night is forgotten


def test_fast_model(analyzer, errors):
    out = [analyzer.process(r, D.FAST, HIGH) for r in raw_night(12)]
    assert {m["event"] for m in out} <= {"normal", "apnea_or_hypopnea"}
    assert all(m["model"] == "fast" and m["carbon_mode"] == "high_carbon" for m in out)
    assert all(errors("apnea-events", m) == [] for m in out)


def test_duplicate_minute_is_skipped(analyzer):
    night = raw_night(5)
    analyzer.process(night[0], D.ACCURATE, LOW)
    assert analyzer.process(night[0], D.ACCURATE, LOW) is None


def test_short_last_minute(analyzer, errors):
    for r in raw_night(3)[:-1]:
        analyzer.process(r, D.ACCURATE, LOW)
    out = analyzer.process(raw_minute(2, is_last=True, seconds=17), D.ACCURATE, LOW)
    assert out["is_last"] and errors("apnea-events", out) == []
    b = D.to_array([1.0, -1.0] * 10, 240)
    assert len(b) == 240 and b.min() == -1.0                    # amplitude kept, not flat


def test_wrong_features_are_refused():
    b = fake_bundle()
    b["features"] = b["features"][::-1]
    with pytest.raises(ValueError):
        D.Model(b, D.ACCURATE)


def test_fast_rule_is_used_as_soon_as_it_is_written(monkeypatch):
    assert D.load_fast_model() is None or D.load_fast_model().kind == D.FAST   # skeleton -> None
    monkeypatch.setattr(D.FM, "predict", lambda row: ("apnea_or_hypopnea", 0.8))
    fast = D.load_fast_model()
    assert fast.kind == D.FAST and fast.version == D.FM.VERSION
    a = D.Analyzer(D.Model(fake_bundle(), D.ACCURATE), fast)
    msg = a.process(raw_minute(0), D.FAST, HIGH)
    assert (msg["model"], msg["event"], msg["model_version"]) == ("fast", "apnea_or_hypopnea", "rule-v1")


def test_without_fast_model_accurate_is_used():
    a = D.Analyzer(D.Model(fake_bundle(), D.ACCURATE))
    assert a.process(raw_minute(0), D.FAST, HIGH)["model"] == "accurate"


# ---------------------------------------------------------------- alert loop (fake Kafka + database)
class Log:
    def __init__(self):
        self.steps, self.sent = [], []

    # producer
    def produce(self, topic, key, value):
        self.steps.append("alert")
        self.sent.append((topic, key, json.loads(value)))

    def flush(self, *_):
        pass

    # database
    def ensure_night(self, *a):
        self.steps.append("row")

    def append_minute(self, raw):
        self.steps.append("minute")


def test_row_first_then_alert_then_minute():
    """alerts.night_id points to raw_nights: the row must exist before the alert goes out."""
    log = Log()
    D.handle_alert_minute(raw_minute(8, spo2=76.0, patient_id="P05"), log, log)
    assert log.steps == ["row", "alert", "minute"]
    assert log.sent[0][:2] == ("alerts", "P05")


def test_alert_goes_out_when_db_is_down():
    class Down(Log):
        def ensure_night(self, *a):
            raise ConnectionError

        def append_minute(self, raw):
            raise ConnectionError

    log = Down()
    D.handle_alert_minute(raw_minute(1, spo2=70.0), log, log)
    assert log.steps == ["alert"]


# ---------------------------------------------------------------- raw_nights (real PostgreSQL)
URL = os.environ.get("APNEA_TEST_DB")


@pytest.mark.skipif(not URL, reason="set APNEA_TEST_DB (docker compose up -d postgres) to run")
def test_raw_nights_minute_by_minute():
    db, night = D.RawNights(URL), f"test-{uuid.uuid4().hex[:8]}"   # apnea_detector may not DELETE
    db.ensure_night(night, "P01", "ucddb")
    assert db.append_minute(raw_minute(0, night_id=night, patient_id="P01"))
    assert not db.append_minute(raw_minute(0, night_id=night, patient_id="P01"))  # duplicate
    assert db.append_minute(raw_minute(2, night_id=night, patient_id="P01"))      # minute 1 missing
    spo2 = db.conn.execute("SELECT spo2 FROM raw_nights WHERE night_id = %s", (night,)).fetchone()[0]
    assert len(spo2) == 180 and spo2[60] is None and spo2[120] == 96.0
