"""Tests of carbon-scheduler (services/carbon-scheduler/carbon_scheduler.py), no Kafka or database."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import carbon_scheduler as C

NIGHT = datetime(2026, 11, 23, 1, 0, tzinfo=C.TZ)
NOON = NIGHT.replace(hour=13)


def test_daily_curve_per_region():
    assert C.curve("NO", NIGHT) < 50 and C.curve("PL", NOON) > 500
    assert C.curve("AT", NIGHT) > 300 > C.curve("AT", NOON)      # AT is dirty at night only


def test_simulated_values_are_repeatable_and_near_the_curve():
    a, b = C.Simulated(["AT", "NO", "PL"], seed=1), C.Simulated(["AT", "NO", "PL"], seed=1)
    va, vb = a.read(NOON), b.read(NOON)
    assert va == vb
    assert all(abs(va[r] - C.curve(r, NOON)) <= C.curve(r, NOON) * 0.031 for r in va)
    with pytest.raises(ValueError):
        C.Simulated(["DE"])


def test_csv_replay_interpolates_and_wraps_midnight():
    src = C.CsvReplay(Path(C.ROOT / "services/carbon-scheduler/carbon_example.csv"), ["AT", "NO", "PL"])
    assert src.read(NIGHT.replace(hour=2))["AT"] == 350.0               # between 00:00 (370) and 04:00 (330)
    assert src.read(NIGHT.replace(hour=22))["AT"] == 345.0              # 20:00 (320) -> 24:00 (370)


def test_first_step_picks_the_cleanest_region_and_sends():
    s = C.Scheduler()
    msg, dec = s.step({"AT": 250, "NO": 30, "PL": 650}, NIGHT)
    assert (msg["region"], msg["mode"], msg["carbon_intensity"]) == ("NO", "low_carbon", 30)
    C.SIGNAL_SCHEMA.validate(msg)
    assert [d["action"] for d in dec] == ["resume"]


def test_no_message_when_nothing_changed():
    s = C.Scheduler()
    s.step({"AT": 250, "NO": 30}, NIGHT)
    assert s.step({"AT": 255, "NO": 31}, NIGHT + timedelta(minutes=1)) == (None, [])


def test_message_when_intensity_moves_more_than_10_percent():
    s = C.Scheduler()
    s.step({"NO": 30}, NIGHT)
    msg, dec = s.step({"NO": 36}, NIGHT + timedelta(minutes=1))
    assert msg["carbon_intensity"] == 36 and dec == []


def test_high_carbon_when_above_threshold():
    s = C.Scheduler()
    s.step({"AT": 250, "PL": 650}, NIGHT)
    msg, dec = s.step({"AT": 360, "PL": 700}, NIGHT + timedelta(minutes=1))
    assert msg["mode"] == "high_carbon" and dec[0]["action"] == "pause"
    assert "360 > 300" in dec[0]["reason"]
    msg, dec = s.step({"AT": 200, "PL": 700}, NIGHT + timedelta(minutes=2))
    assert msg["mode"] == "low_carbon" and dec[0]["action"] == "resume"


def test_move_only_if_20_percent_cleaner_and_15_minutes_passed():
    s = C.Scheduler()
    s.step({"AT": 200, "PL": 650}, NIGHT)                                 # starts in AT
    assert s.step({"AT": 200, "PL": 170}, NIGHT + timedelta(minutes=20))[0] is None   # only 15 % cleaner
    assert s.region == "AT"
    s2 = C.Scheduler()
    s2.step({"AT": 200, "PL": 650}, NIGHT)
    assert s2.step({"AT": 200, "PL": 100}, NIGHT + timedelta(minutes=10)) == (None, [])   # too soon
    msg, dec = s2.step({"AT": 200, "PL": 100}, NIGHT + timedelta(minutes=16))
    assert msg["region"] == "PL" and dec[0]["action"] == "move"


def test_force_mode():
    s = C.Scheduler(force_mode="high_carbon")
    msg, dec = s.step({"NO": 30}, NIGHT)
    assert msg["mode"] == "high_carbon" and "FORCE_MODE" in dec[0]["reason"]
    with pytest.raises(ValueError):
        C.Scheduler(force_mode="green")


def test_sim_clock_speed():
    t = [100.0]
    clock = C.SimClock("22:00", speed=60, real=lambda: t[0])
    assert clock.now().strftime("%H:%M") == "22:00"
    t[0] += 90                                                             # 90 s real = 90 min simulated
    assert clock.now().strftime("%H:%M") == "23:30"


def test_loop_sends_and_logs():
    class P:
        sent = []

        def produce(self, topic, key, value):
            self.sent.append((topic, key, json.loads(value)))

        def flush(self, t):
            return 0

    class DB:
        rows = []

        def insert(self, d, at):
            self.rows.append(d["action"])

    class Clock:
        def now(self):
            return NIGHT

    n = [0]

    def stop():
        n[0] += 1
        return n[0] > 3

    p, db = P(), DB()
    C.run(p, C.Simulated(["AT", "NO", "PL"]), C.Scheduler(), Clock(), db, stop, sleep=lambda s: None)
    assert p.sent[0][0] == "carbon-signal" and p.sent[0][1] == "NO" and db.rows == ["resume"]
