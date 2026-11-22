"""Tests for services/model-trainer/carbon_wait.py, without a real Kafka:  pytest

A fake consumer returns prepared carbon-signal messages; a fake clock makes the timeout instant.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "model-trainer"))
import carbon_wait as W  # noqa: E402


def signal(mode, region="NO", intensity=35.0):
    return {"region": region, "carbon_intensity": intensity, "mode": mode,
            "sent_at": "2026-11-23T02:00:00+00:00"}


class Msg:
    def __init__(self, value):
        self._value = value if isinstance(value, bytes) else json.dumps(value).encode()

    def value(self):
        return self._value

    def error(self):
        return None


class FakeConsumer:
    """poll() returns the prepared messages one after the other, then None (nothing new)."""

    def __init__(self, *messages, high=1):
        self.messages = [m if m is None else Msg(m) for m in messages]
        self.high, self.assigned = high, None

    def list_topics(self, topic, timeout=None):
        return SimpleNamespace(topics={topic: SimpleNamespace(partitions={0: None})})

    def get_watermark_offsets(self, tp, timeout=None):
        return 0, self.high

    def assign(self, partitions):
        self.assigned = [(p.topic, p.partition, p.offset) for p in partitions]

    def poll(self, timeout):
        return self.messages.pop(0) if self.messages else None


class FakeClock:
    """Every call is one second later."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 1.0
        return self.t


def wait(consumer, timeout_s=100):
    return W.wait_for_low_carbon(consumer=consumer, clock=FakeClock(), timeout_s=timeout_s)


def test_starts_at_the_newest_message():
    c = FakeConsumer(signal("low_carbon"), high=5)
    wait(c)
    assert c.assigned == [("carbon-signal", 0, 4)]           # offset high - 1 = the newest
    empty = FakeConsumer(signal("low_carbon"), high=0)
    wait(empty)
    assert empty.assigned == [("carbon-signal", 0, 0)]       # empty topic: from the start


def test_low_carbon_now_returns_at_once():
    assert wait(FakeConsumer(signal("low_carbon", "AT", 120))) == signal("low_carbon", "AT", 120)


def test_high_then_low_returns_the_low_message():
    c = FakeConsumer(signal("high_carbon", "PL", 650), None, None, signal("low_carbon", "NO", 30))
    assert wait(c)["region"] == "NO"


def test_only_high_carbon_gives_up(caplog):
    with pytest.raises(W.NoLowCarbonWindow):
        wait(FakeConsumer(signal("high_carbon")), timeout_s=10)


def test_empty_topic_keeps_waiting_until_a_message_comes():
    c = FakeConsumer(None, None, None, signal("low_carbon"), high=0)
    assert W.is_low_carbon(wait(c))


def test_bad_message_is_ignored():
    c = FakeConsumer(b"not json", {"mode": "low_carbon"}, signal("low_carbon"))   # 2nd: no region
    assert wait(c) == signal("low_carbon")
