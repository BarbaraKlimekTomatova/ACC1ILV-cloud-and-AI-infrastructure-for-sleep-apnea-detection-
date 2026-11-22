"""Tests for data/03_to_kafka_messages.py: every message must be valid against kafka/schemas/."""

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "kafka" / "schemas"

spec = importlib.util.spec_from_file_location("to_kafka", ROOT / "data" / "03_to_kafka_messages.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def validator(topic):
    schema = json.loads((SCHEMAS / f"{topic}-value.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def one_minute(spo2=96.0):
    return {"spo2": np.full(60, spo2), "flow": np.zeros(240),
            "thorax": np.zeros(240), "abdomen": np.zeros(240)}


@pytest.mark.parametrize("topic", ["raw-signals", "alerts", "apnea-events",
                                   "night-results", "carbon-signal"])
def test_examples_are_valid(topic):
    example = json.loads((ROOT / "kafka" / "examples" / f"{topic}-value.example.json").read_text(encoding="utf-8"))
    validator(topic).validate(example)


def test_raw_signals_message_is_valid_and_nan_becomes_null():
    signals = one_minute()
    signals["spo2"][3] = np.nan
    msg = M.build_raw_signals_message("ucddb025", "P05", "ucddb", 8, signals, False)
    validator("raw-signals").validate(msg)
    assert msg["spo2"][3] is None and len(msg["spo2"]) == 60 and len(msg["flow"]) == 240


def test_raw_signals_rejects_bad_input():
    with pytest.raises(ValueError):
        M.build_raw_signals_message("x", "P01", "other", 0, one_minute(), False)
    too_long = one_minute()
    too_long["flow"] = np.zeros(241)
    with pytest.raises(ValueError):
        M.build_raw_signals_message("x", "P01", "ucddb", 0, too_long, False)


def test_write_night_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "OUT", tmp_path)
    path, minutes = M.write_night("ucddb025")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == minutes == 355
    v = validator("raw-signals")
    msgs = [json.loads(line) for line in lines]
    for msg in msgs:
        v.validate(msg)
    assert [m["minute"] for m in msgs] == list(range(minutes))
    assert [m["is_last"] for m in msgs] == [False] * (minutes - 1) + [True]
    assert {m["patient_id"] for m in msgs} == {"P05"}
    assert msgs[8]["sent_at"] == "2026-11-20T22:08:00+00:00"
    # no labels in the messages
    assert not {"apnea", "event", "sleep_stage", "usable"} & set(msgs[0])
    # same values as the clean file (float16 -> rounded)
    clean = np.load(ROOT / "data" / "clean" / "signals" / "ucddb025.npz")
    assert math.isclose(msgs[8]["flow"][0], float(clean["flow"][8 * 240]), abs_tol=1e-3)


def test_alert_message():
    msg = M.build_alert_message("P05", "ucddb025", 8, 76.04)
    validator("alerts").validate(msg)
    assert msg["spo2_min"] == 76.0 and msg["threshold"] == 80
    with pytest.raises(ValueError):
        M.build_alert_message("P05", "ucddb025", 8, 80.0)


def test_carbon_signal_message():
    msg = M.build_carbon_signal_message("NO", 35, "low_carbon")
    validator("carbon-signal").validate(msg)
    with pytest.raises(ValueError):
        M.build_carbon_signal_message("DE", 35, "low_carbon")
    with pytest.raises(ValueError):
        M.build_carbon_signal_message("NO", 35, "medium")
