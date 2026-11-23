"""Tests of alert-check (services/alert-check/alert_check.py), no Kafka needed."""

import json
import math
from datetime import datetime, timezone

import pytest

import alert_check as A


def raw(spo2, minute=7):
    return {"patient_id": "P05", "night_id": "ucddb025", "source": "ucddb", "minute": minute,
            "is_last": False, "spo2": spo2, "flow": [0.0] * 240, "thorax": [0.0] * 240,
            "abdomen": [0.0] * 240, "sent_at": "2026-11-23T22:00:00+00:00"}


def test_below_80_is_an_alert():
    a = A.alert_for(raw([95.0] * 59 + [78.0]), now=datetime(2026, 11, 23, tzinfo=timezone.utc))
    assert a == {"patient_id": "P05", "night_id": "ucddb025", "minute": 7, "spo2_min": 78.0,
                 "threshold": 80.0, "detected_at": "2026-11-23T00:00:00+00:00"}


def test_80_and_above_is_no_alert():
    assert A.alert_for(raw([80.0] * 60)) is None


def test_dropouts_and_artefacts_are_ignored():
    assert A.alert_for(raw([None] * 60)) is None
    assert A.alert_for(raw([95.0] * 30 + [math.nan] * 29 + [12.0])) is None      # 12 % = artefact
    assert A.alert_for(raw([None] * 59 + [75.0]))["spo2_min"] == 75.0


def test_rounding_never_reaches_the_threshold():
    a = A.alert_for(raw([79.97] * 60))
    assert a["spo2_min"] < 80


# ---------------------------------------------------------------- loop with fake Kafka
class Msg:
    def __init__(self, value):
        self._v = value

    def value(self):
        return self._v

    def error(self):
        return None


class FakeConsumer:
    def __init__(self, values):
        self.queue, self.stored, self.closed = [Msg(v) for v in values], [], False

    def subscribe(self, topics):
        self.topics = topics

    def poll(self, timeout):
        return self.queue.pop(0) if self.queue else None

    def store_offsets(self, msg):
        self.stored.append(msg)

    def close(self):
        self.closed = True


class FakeProducer:
    def __init__(self, undelivered=0):
        self.sent, self.undelivered = [], undelivered

    def produce(self, topic, key, value):
        self.sent.append((topic, key, json.loads(value)))

    def flush(self, timeout):
        return self.undelivered


def test_loop_sends_alerts_and_stores_every_offset():
    msgs = [json.dumps(raw([97.0] * 60, 0)).encode(), b"not json", json.dumps(raw([70.0] * 60, 1)).encode()]
    c, p = FakeConsumer(msgs), FakeProducer()
    A.run(c, p, stop=lambda: not c.queue and len(c.stored) == 3)
    assert c.topics == ["raw-signals"]
    assert [(t, k, m["minute"]) for t, k, m in p.sent] == [("alerts", "P05", 1)]
    assert len(c.stored) == 3 and c.closed


def test_offset_is_not_stored_when_the_alert_was_not_delivered():
    c, p = FakeConsumer([json.dumps(raw([70.0] * 60)).encode()]), FakeProducer(undelivered=1)
    with pytest.raises(RuntimeError):
        A.run(c, p, stop=lambda: False)
    assert c.stored == []
