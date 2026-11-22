"""Tests for the apnea-events and night-results builders in data/03_to_kafka_messages.py
(owner: Barbara): every message must be valid against kafka/schemas/."""

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("to_kafka_results", ROOT / "data" / "03_to_kafka_messages.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def errors(topic, message):
    schema = json.loads((ROOT / "kafka" / "schemas" / f"{topic}-value.schema.json").read_text(encoding="utf-8"))
    return [e.message for e in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(message)]


# ---------------------------------------------------------------- apnea-events
def test_apnea_event_accurate_minute():
    msg = M.build_apnea_event_message("P03", "ucddb013", 114, "hypopnea", 0.87654, "accurate",
                                      "low_carbon", False, model_version="accurate-v1", region="NO")
    assert errors("apnea-events", msg) == []
    assert msg["probability"] == 0.877 and "kwh" not in msg        # energy only on the last minute


def test_apnea_event_last_minute_has_energy():
    msg = M.build_apnea_event_message("P03", "ucddb013", 404, "normal", 0.9, "accurate", "low_carbon",
                                      True, model_version="accurate-v1", region="NO",
                                      kwh=1.5e-05, gco2=0.000525)
    assert errors("apnea-events", msg) == []
    assert msg["is_last"] is True and msg["kwh"] == 1.5e-05 and msg["gco2"] == 0.000525


def test_apnea_event_fast_model_has_no_type():
    msg = M.build_apnea_event_message("P05", "ucddb025", 8, "apnea_or_hypopnea", 0.7, "fast",
                                      "high_carbon", False, model_version="rule-v1", region="PL")
    assert errors("apnea-events", msg) == []


def test_apnea_event_rejects_bad_input():
    with pytest.raises(ValueError):
        M.build_apnea_event_message("P01", "x", 0, "snoring", 0.5, "accurate", "low_carbon", False)
    with pytest.raises(ValueError):
        M.build_apnea_event_message("P01", "x", 0, "normal", 0.5, "medium", "low_carbon", False)


# ---------------------------------------------------------------- night-results
def test_night_result_with_llm_summary():
    msg = M.build_night_result_message(
        "P03", "ucddb013", 11.94, "mild", event_count=80, apnea_count=3, hypopnea_count=77,
        minutes=405, model="accurate", model_version="accurate-v1", carbon_mode="low_carbon",
        region="NO", kwh=1.5e-05, gco2=0.000525, deadline_met=True,
        llm_summary="AHI 11.9, mild. Routine review.", llm_model="llama3.2:1b", llm_gco2=0.00012)
    assert errors("night-results", msg) == []
    assert msg["ahi"] == 11.9


def test_night_result_fast_model_without_summary():
    msg = M.build_night_result_message("P05", "ucddb025", 53.7, "severe", event_count=191,
                                       minutes=355, model="fast", carbon_mode="high_carbon")
    assert errors("night-results", msg) == []                      # counts and summary = null
    assert msg["apnea_count"] is None and msg["llm_summary"] is None


def test_night_result_rejects_unknown_severity():
    with pytest.raises(ValueError):
        M.build_night_result_message("P01", "x", 3.0, "light")
