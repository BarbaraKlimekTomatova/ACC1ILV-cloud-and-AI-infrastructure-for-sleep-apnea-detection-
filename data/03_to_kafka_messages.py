"""Step 3: turn the clean nights into Kafka messages.   (SKELETON, not done yet)

Usage (when it is done):
    python data/03_to_kafka_messages.py

Input:   data/clean/signals/<night>.npz   (from 02_clean.py)
         data/clean/splits.json
Output:  data/kafka_messages/<night>.jsonl   one line = one minute = one message

Our system has 5 Kafka topics. They are listed below in the order the data
flows through the system (best practice: read the file top to bottom and you
follow one night from the device to the doctor; the control topic is last).

    1. raw-signals    device-simulator  -> apnea-detector, alert-check   (Aliénor)
    2. alerts         alert-check       -> alert-service                 (Aliénor)
    3. apnea-events   apnea-detector    -> ahi-triage                    (Barbara)
    4. night-results  ahi-triage        -> doctor-dashboard              (Barbara)
    5. carbon-signal  carbon-scheduler  -> apnea-detector                (Aliénor)

Only message 1 is built from our data files. Messages 2-5 are built by the
services while the system runs; their builders are here so the whole team
uses the same message shape (field names, types) in one place.

Labels (labels.csv) never go into any message: the live system must not
know the answers.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent
CLEAN = DATA / "clean"
OUT = DATA / "kafka_messages"

SIGNALS = {"spo2": 1, "flow": 4, "thorax": 4, "abdomen": 4}   # Hz


# ---------------------------------------------------------------- 1. raw-signals


def build_raw_signals_message(night_id, patient_id, source, minute, signals, is_last):
    """Topic raw-signals, one minute of device data (no labels)."""
    # TODO: Aliénor
    raise NotImplementedError


def write_night(night_id):
    """Write data/kafka_messages/<night_id>.jsonl, one raw-signals message per line."""
    # TODO: Aliénor
    raise NotImplementedError


# ---------------------------------------------------------------- 2. alerts


def build_alert_message(patient_id, night_id, minute, spo2_min):
    """Topic alerts, sent right away when SpO2 < 80 %."""
    # TODO: Aliénor
    raise NotImplementedError


# ---------------------------------------------------------------- 3. apnea-events


EVENTS = ("apnea", "hypopnea", "normal", "apnea_or_hypopnea")


def build_apnea_event_message(patient_id, night_id, minute, event, probability,
                              model, carbon_mode, is_last,
                              model_version=None, region=None,
                              kwh=None, gco2=None):
    """Topic apnea-events, the detector's answer for one minute.

    event        "apnea", "hypopnea" or "normal" (accurate model, 3 classes);
                 the fast model cannot tell the type, it sends "apnea_or_hypopnea"
    probability  0-1, how sure the model is that this minute is an apnea
    model        "fast" or "accurate"
    kwh, gco2    CodeCarbon for the whole night, only on the last minute
    """
    if event not in EVENTS:
        raise ValueError(f"event must be one of {EVENTS}, not {event!r}")
    if model not in ("fast", "accurate"):
        raise ValueError(f"model must be 'fast' or 'accurate', not {model!r}")

    message = {
        "patient_id": patient_id,          # Kafka key
        "night_id": night_id,
        "minute": int(minute),
        "event": event,
        "probability": round(float(probability), 3),   # of the chosen event
        "model": model,
        "model_version": model_version,
        "carbon_mode": carbon_mode,        # low_carbon or high_carbon
        "region": region,                  # AT, NO or PL
        "is_last": bool(is_last),
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    if is_last:
        message["kwh"] = kwh
        message["gco2"] = gco2
    return message


# ---------------------------------------------------------------- 4. night-results


def build_night_result_message(patient_id, night_id, ahi, severity,
                               event_count=None, apnea_count=None,
                               hypopnea_count=None, minutes=None,
                               model=None, model_version=None,
                               carbon_mode=None, region=None,
                               kwh=None, gco2=None, deadline_met=None):
    """Topic night-results, AHI and severity of one finished night.

    The same fields as the table results, so ahi-triage can send the row
    it just saved, and the dashboard does not need to read the database
    to show a new night.
    """
    if severity not in ("normal", "mild", "moderate", "severe"):
        raise ValueError(f"unknown severity {severity!r}")

    return {
        "patient_id": patient_id,          # Kafka key
        "night_id": night_id,
        "ahi": round(float(ahi), 1),       # events per hour
        "severity": severity,
        "event_count": event_count,        # apnea + hypopnea (+ untyped)
        "apnea_count": apnea_count,
        "hypopnea_count": hypopnea_count,
        "minutes": minutes,                # length of the night
        "model": model,
        "model_version": model_version,
        "carbon_mode": carbon_mode,
        "region": region,
        "kwh": kwh,
        "gco2": gco2,
        "deadline_met": deadline_met,      # ready before 08:00?
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------- 5. carbon-signal


def build_carbon_signal_message(region, intensity_g_per_kwh, mode):
    """Topic carbon-signal, the current carbon mode (low_carbon | high_carbon)."""
    # TODO: Aliénor
    raise NotImplementedError


# ---------------------------------------------------------------- main


def main():
    """Write all nights from data/clean/splits.json to data/kafka_messages/."""
    # TODO: Aliénor
    raise NotImplementedError


if __name__ == "__main__":
    main()
