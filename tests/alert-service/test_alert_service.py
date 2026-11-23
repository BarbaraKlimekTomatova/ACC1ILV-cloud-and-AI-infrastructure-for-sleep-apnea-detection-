"""Tests of alert-service (services/alert-service/alert_service.py), no Kafka or database needed."""

import json
from datetime import datetime, timedelta, timezone

import alert_service as S

T0 = datetime(2026, 11, 23, 22, 0, tzinfo=timezone.utc)


def alert(minute=7, night="ucddb025"):
    return {"patient_id": "P05", "night_id": night, "minute": minute, "spo2_min": 78.0,
            "threshold": 80.0, "detected_at": T0.isoformat()}


class FakeTable:
    """Like the alerts table: skips the same night + minute, FK error for unknown nights."""

    def __init__(self, nights=("ucddb025",), appears_after=None):
        self.nights, self.rows, self.calls, self.appears_after = set(nights), [], 0, appears_after

    def insert(self, p):
        self.calls += 1
        if self.appears_after and self.calls > self.appears_after:
            self.nights.add(p["night_id"])
        if p["night_id"] not in self.nights:
            raise S.MissingNight(p["night_id"])
        if any((r["night_id"], r["minute"]) == (p["night_id"], p["minute"]) for r in self.rows):
            return None
        self.rows.append(p)
        return len(self.rows), p["detected_at"] + timedelta(seconds=0.3)


def parsed(a):
    return S.parse_alert(json.dumps(a).encode())


def test_parse_valid_and_invalid():
    assert parsed(alert())["detected_at_dt"] == T0
    assert S.parse_alert(b"{}") is None
    bad = alert()
    bad["spo2_min"] = 85.0                         # not an alert (schema: < 80)
    assert parsed(bad) is None


def test_store_once_then_duplicate():
    db = FakeTable()
    assert S.store(db, parsed(alert()))[0] == "stored"
    assert S.store(db, parsed(alert())) == "duplicate"
    assert len(db.rows) == 1 and db.rows[0]["spo2_min"] == 78.0


def test_waits_for_the_raw_nights_row():
    db, slept = FakeTable(nights=(), appears_after=2), []
    assert S.store(db, parsed(alert()), sleep=slept.append, fk_wait_s=60)[0] == "stored"
    assert len(slept) == 2


def test_drops_when_the_night_never_comes():
    t = [0.0]

    def sleep(s):
        t[0] += s

    db = FakeTable(nights=())
    assert S.store(db, parsed(alert()), fk_wait_s=3, retry_s=1, sleep=sleep, clock=lambda: t[0]) == "dropped"


def test_latency():
    assert S.latency_s(T0, T0 + timedelta(seconds=1.5)) == 1.5
    assert S.latency_s(T0, T0 - timedelta(seconds=1)) == 0.0     # clocks a bit off


class Msg:
    def __init__(self, v):
        self.v = v

    def value(self):
        return self.v

    def error(self):
        return None


class FakeConsumer:
    def __init__(self, values):
        self.queue, self.stored = [Msg(v) for v in values], []

    def subscribe(self, topics):
        self.topics = topics

    def poll(self, timeout):
        return self.queue.pop(0) if self.queue else None

    def store_offsets(self, m):
        self.stored.append(m)

    def close(self):
        pass


def test_loop_stores_rows_and_offsets():
    vals = [json.dumps(alert(1)).encode(), json.dumps(alert(1)).encode(), b"garbage", json.dumps(alert(2)).encode()]
    c, db = FakeConsumer(vals), FakeTable()
    S.run(c, db, stop=lambda: not c.queue)
    assert c.topics == ["alerts"]
    assert [r["minute"] for r in db.rows] == [1, 2] and len(c.stored) == 4


def test_sql_skips_duplicates_and_returns_stored_at():
    sql = " ".join(S.INSERT_SQL.split())
    assert "WHERE NOT EXISTS" in sql and "RETURNING alert_id, stored_at" in sql
