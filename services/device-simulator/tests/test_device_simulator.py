"""Tests for the device-simulator: no Kafka needed (a fake producer records the messages)."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("device_simulator", ROOT / "services" / "device-simulator" / "main.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


class FakeProducer:
    def __init__(self, full_times=0):
        self.sent = []
        self.full_times = full_times           # raise BufferError this many times first
        self.polls = 0

    def produce(self, topic, key, value):
        if self.full_times:
            self.full_times -= 1
            raise BufferError("queue full")
        self.sent.append((topic, key, json.loads(value)))

    def poll(self, timeout=0):
        self.polls += 1


class FakeClock:
    """time.monotonic + time.sleep that do not really wait."""

    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(round(s, 6))
        self.t += s


def minute(night_id, patient_id, m, is_last=False):
    return {"patient_id": patient_id, "night_id": night_id, "source": "ucddb", "minute": m,
            "is_last": is_last, "sent_at": f"2026-11-20T22:{m:02d}:00+00:00",
            "spo2": [95.0] * 60, "flow": [0.0] * 240, "thorax": [0.0] * 240, "abdomen": [0.0] * 240}


def write_night(folder, night_id, patient_id, minutes):
    lines = [json.dumps(minute(night_id, patient_id, m, m == minutes - 1)) for m in range(minutes)]
    (folder / f"{night_id}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def folder(tmp_path):
    write_night(tmp_path, "ucddb025", "P05", 3)
    write_night(tmp_path, "ucddb010", "P04", 2)
    return tmp_path


@pytest.fixture(autouse=True)
def not_stopped():
    S.stop.clear()
    yield
    S.stop.clear()


def test_choose_nights(folder):
    assert S.choose_nights(folder, ["ucddb025"]) == ["ucddb025"]
    assert S.choose_nights(folder, all_nights=True) == ["ucddb010", "ucddb025"]
    with pytest.raises(FileNotFoundError):
        S.choose_nights(folder)                     # demo nights ucddb018 ... are missing here


def test_interleave_minute_by_minute(folder):
    nights = S.plan(folder, ["ucddb025", "ucddb010"])
    order = [(m["night_id"], m["minute"]) for _, m in S.interleave(nights)]
    assert order == [("ucddb025", 0), ("ucddb010", 0), ("ucddb025", 1), ("ucddb010", 1),
                     ("ucddb025", 2)]


def test_copies_get_a_new_night_id(folder):
    nights = S.plan(folder, ["ucddb025"], copies=3)
    assert list(nights) == ["ucddb025", "ucddb025-2", "ucddb025-3"]
    assert {m["patient_id"] for ms in nights.values() for m in ms} == {"P05"}
    assert [m["night_id"] for m in nights["ucddb025-2"]] == ["ucddb025-2"] * 3


def test_run_sends_every_minute_with_patient_key(folder):
    p, c = FakeProducer(), FakeClock()
    result = S.run(p, S.plan(folder, ["ucddb025", "ucddb010"]), speed=0,
                   clock=c.clock, sleep=c.sleep)
    assert result == {"sent": 5, "invalid": 0}
    assert all(topic == "raw-signals" and key == m["patient_id"] for topic, key, m in p.sent)
    assert [m["is_last"] for _, _, m in p.sent if m["night_id"] == "ucddb025"] == [False, False, True]
    assert c.sleeps == []                            # burst: no waiting


def test_speed_paces_the_night_minutes(folder):
    p, c = FakeProducer(), FakeClock()
    S.run(p, S.plan(folder, ["ucddb025", "ucddb010"]), speed=60, clock=c.clock, sleep=c.sleep)
    assert c.sleeps == [1.0, 1.0]                    # 60x: one night-minute per second, both nights together
    assert c.t == pytest.approx(2.0)


def test_wait_seconds():
    assert S.wait_seconds(10, 0, 0, 5) == 0          # burst
    assert S.wait_seconds(10, 60, 0, 5) == 5         # minute 10 at 60x is due at 10 s
    assert S.wait_seconds(10, 1, 0, 0) == 600        # real time
    assert S.wait_seconds(1, 60, 0, 99) == 0         # late: no negative wait


def test_sent_at_is_send_time_unless_keep_time(folder):
    m = minute("ucddb025", "P05", 8)
    assert S.prepare(m, keep_time=True)["sent_at"] == "2026-11-20T22:08:00+00:00"
    assert S.prepare(m)["sent_at"] != m["sent_at"]


def test_invalid_message_is_not_sent(folder):
    nights = S.plan(folder, ["ucddb025"])
    nights["ucddb025"][1]["spo2"] = []               # minItems 1
    p = FakeProducer()
    result = S.run(p, nights, speed=0)
    assert result == {"sent": 2, "invalid": 1}
    assert [m["minute"] for _, _, m in p.sent] == [0, 2]


def test_full_queue_waits_and_retries(folder):
    p = FakeProducer(full_times=2)
    assert S.run(p, S.plan(folder, ["ucddb010"]), speed=0)["sent"] == 2
    assert len(p.sent) == 2


def test_stop_ends_the_run(folder):
    S.stop.set()
    assert S.run(FakeProducer(), S.plan(folder, ["ucddb025"]), speed=0)["sent"] == 0


def test_args():
    assert S.parse_args(["--burst"]).speed == 0
    assert S.parse_args(["ucddb025", "--speed", "600"]).nights == ["ucddb025"]
    with pytest.raises(SystemExit):
        S.parse_args(["--copies", "0"])


def test_real_demo_night_is_valid():
    """With the generated files (if they exist): every message of a demo night passes the schema."""
    path = S.MESSAGES_DIR / "ucddb025.jsonl"
    if not path.exists():
        pytest.skip("run python data/03_to_kafka_messages.py --split demo first")
    p = FakeProducer()
    result = S.run(p, S.plan(S.MESSAGES_DIR, ["ucddb025"]), speed=0)
    assert result == {"sent": 355, "invalid": 0}
    assert p.sent[-1][2]["is_last"] is True
