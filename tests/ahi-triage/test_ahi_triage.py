"""ahi-triage tests in one file: AHI, severity, deadline, duplicates, safe Kafka offsets,
and the results table with a real PostgreSQL (optional). No Kafka needed."""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "ahi-triage"))

import ahi_triage as T  # noqa: E402

VIE = ZoneInfo("Europe/Vienna")


def errors(topic, message):
    schema = json.loads((ROOT / "kafka" / "schemas" / f"{topic}-value.schema.json").read_text())
    return [e.message for e in Draft202012Validator(schema).iter_errors(message)]


def at(h, m=0, day=21):
    return datetime(2026, 11, day, h, m, tzinfo=VIE)


def event(minute, kind="normal", is_last=False, night_id="ucddb013", model="accurate"):
    msg = {"patient_id": "P03", "night_id": night_id, "minute": minute, "event": kind,
           "probability": 0.9, "model": model, "model_version": f"{model}-v1",
           "carbon_mode": "low_carbon" if model == "accurate" else "high_carbon", "region": "NO",
           "is_last": is_last, "sent_at": "2026-11-20T23:00:00+00:00"}
    if is_last:
        msg["kwh"], msg["gco2"] = 0.00002, 0.0007
    return msg


def night(minutes=60, apnea=(10, 11, 12), hypopnea=(30, 31, 32), **kw):
    out = []
    for m in range(minutes):
        kind = "apnea" if m in apnea else "hypopnea" if m in hypopnea else "normal"
        out.append(event(m, kind, is_last=m == minutes - 1, **kw))
    return out


class FixedClock:
    def __init__(self, *times):
        self.times = list(times)

    def now(self):
        return self.times.pop(0) if len(self.times) > 1 else self.times[0]


# ---------------------------------------------------------------- AHI and severity
def test_severity_limits():
    assert [T.severity(a) for a in (0, 4.9, 5, 14.9, 15, 29.9, 30, 80)] == \
        ["normal", "normal", "mild", "mild", "moderate", "moderate", "severe", "severe"]


def test_one_hour_with_six_events():
    t = T.Triage(FixedClock(at(23), at(7, day=22)))
    out = [t.handle(m) for m in night()]
    assert out[:-1] == [None] * 59
    r = out[-1]
    assert r["ahi"] == 6.0 and r["severity"] == "mild" and r["minutes"] == 60
    assert r["event_count"] == 6 and r["apnea_count"] == 3 and r["hypopnea_count"] == 3
    assert r["model"] == "accurate" and r["region"] == "NO" and r["gco2"] == 0.0007
    assert r["deadline_met"] is True
    assert errors("night-results", r) == []


def test_duplicate_minute_counted_once():
    t = T.Triage(FixedClock(at(23)))
    msgs = night(60)
    for m in msgs[:20]:
        t.handle(m)
    t.handle(msgs[11])                          # Kafka delivered minute 11 again
    r = [t.handle(m) for m in msgs[20:]][-1]
    assert r["event_count"] == 6


def test_fast_model_has_no_apnea_hypopnea_split():
    t = T.Triage(FixedClock(at(23)))
    msgs = night(30, apnea=(), hypopnea=(), model="fast")
    msgs[5]["event"] = msgs[6]["event"] = "apnea_or_hypopnea"
    r = [t.handle(m) for m in msgs][-1]
    assert r["event_count"] == 2 and r["ahi"] == 4.0
    assert r["apnea_count"] is None and r["hypopnea_count"] is None
    assert errors("night-results", r) == []


def test_deadline():
    start = at(23)
    assert T.next_deadline(start) == at(8, day=22)
    late = T.Triage(FixedClock(start, at(9, day=22)))
    assert [late.handle(m) for m in night(3)][-1]["deadline_met"] is False


def test_late_duplicate_and_already_saved_are_not_sent_again():
    t = T.Triage(FixedClock(at(23)))
    msgs = night(5)
    assert [t.handle(m) for m in msgs][-1] is not None
    assert t.handle(msgs[-1]) is None           # duplicate of the last minute
    assert t.handle(msgs[2]) is None and t.nights == {}

    again = T.Triage(FixedClock(at(23)), already_saved=lambda nid: True)
    assert [again.handle(m) for m in msgs][-1] is None   # read again after a restart


# ---------------------------------------------------------------- Kafka offsets (UC2 A3)
def test_offset_waits_for_the_oldest_unfinished_night():
    o = T.Offsets()
    o.seen(0, 100, "A")                         # night A starts
    o.seen(0, 101, "B")                         # night B starts on the same partition
    o.seen(0, 102, "A")
    assert o.safe(0) == 100                     # A and B are open: restart reads from 100
    o.done(0, "A")
    assert o.safe(0) == 101                     # B still open
    o.seen(0, 103, "B")
    o.done(0, "B")
    assert o.safe(0) == 104                     # nothing open: past the last message
    assert o.safe(1) is None                    # nothing seen on partition 1


# ---------------------------------------------------------------- results table (real PostgreSQL)
DETECTOR_DB = os.environ.get("APNEA_TEST_DB")
TRIAGE_DB = os.environ.get("AHI_TEST_DB") or (DETECTOR_DB or "").replace(
    "apnea_detector:dev_apnea_detector", "ahi_triage:dev_ahi_triage")


@pytest.mark.skipif(not DETECTOR_DB, reason="set APNEA_TEST_DB (docker compose up -d postgres) to run")
def test_results_row():
    import psycopg
    nid = f"test-{uuid.uuid4().hex[:8]}"        # the services may not DELETE
    with psycopg.connect(DETECTOR_DB, autocommit=True) as det:     # raw_nights row (FK)
        det.execute("INSERT INTO raw_nights (night_id, patient_id, source, spo2, flow, thorax, abdomen) "
                    "VALUES (%s, 'P01', 'ucddb', '[]', '[]', '[]', '[]')", (nid,))
    db = T.Results(TRIAGE_DB)
    assert not db.exists(nid)
    r = [T.Triage(FixedClock(at(23))).handle(m) for m in night(10, night_id=nid)][-1]
    db.save(r)
    assert db.exists(nid)
    row = db.conn.execute("SELECT ahi, severity, event_count, model, deadline_met, llm_summary "
                          "FROM results WHERE night_id = %s", (nid,)).fetchone()
    assert row == (pytest.approx(r["ahi"]), r["severity"], r["event_count"], "accurate", True, None)
