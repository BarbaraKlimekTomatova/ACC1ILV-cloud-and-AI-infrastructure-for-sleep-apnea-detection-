"""Step 3: turn the clean nights into Kafka messages.

Usage:
    python data/03_to_kafka_messages.py               # all 33 nights
    python data/03_to_kafka_messages.py --split demo  # only the 5 demo nights
    python data/03_to_kafka_messages.py ucddb025      # one or more nights by id

Input:   data/clean/signals/<night>.npz   (from 02_clean.py)
         data/clean/splits.json
Output:  kafka/messages/raw-signals/<night>.jsonl   one line = one minute = one message

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

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent
CLEAN = DATA / "clean"
OUT = DATA.parent / "kafka" / "messages" / "raw-signals"

SIGNALS = {"spo2": 1, "flow": 4, "thorax": 4, "abdomen": 4}   # Hz
DECIMALS = {"spo2": 1, "flow": 3, "thorax": 3, "abdomen": 3}  # same as kafka/examples/

# The 5 demo nights belong to the demo patients P01-P05 (db/init/09_insert_demo_patients.sql).
# All other nights keep their PhysioNet id as patient_id (they are not in the patients table).
DEMO_PATIENTS = {"ucddb018": "P01", "ucddb017": "P02", "ucddb013": "P03",
                 "ucddb010": "P04", "ucddb025": "P05"}

# Fixed start of every night, so the files are the same each time we build them:
# minute 0 = 22:00 UTC, minute 8 = 22:08 (as in the example). The device-simulator
# can put the real send time in sent_at when it replays a night.
NIGHT_START = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)

ALERT_THRESHOLD = 80.0      # % SpO2
REGIONS = ("AT", "NO", "PL")
CARBON_MODES = ("low_carbon", "high_carbon")
SOURCES = ("ucddb", "apnea-ecg")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _to_list(values, decimals):
    """numpy array -> JSON list; NaN (sensor drop-out) -> null."""
    rounded = np.round(np.asarray(values, dtype=np.float64), decimals)
    return [None if math.isnan(v) else v for v in rounded.tolist()]


# ---------------------------------------------------------------- 1. raw-signals


def build_raw_signals_message(night_id, patient_id, source, minute, signals, is_last,
                              sent_at=None):
    """Topic raw-signals, one minute of device data (no labels).

    signals   dict with the values of this minute: spo2 (60 at 1 Hz),
              flow / thorax / abdomen (240 at 4 Hz); NaN becomes null
    sent_at   ISO time; None = now
    """
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, not {source!r}")
    if int(minute) < 0:
        raise ValueError(f"minute must be >= 0, not {minute}")

    message = {
        "patient_id": patient_id,          # Kafka key
        "night_id": night_id,
        "source": source,
        "minute": int(minute),
        "is_last": bool(is_last),
        "sent_at": sent_at or _now(),
    }
    for name, hz in SIGNALS.items():
        values = _to_list(signals[name], DECIMALS[name])
        if not 1 <= len(values) <= 60 * hz:
            raise ValueError(f"{name}: {len(values)} values, expected 1-{60 * hz}")
        message[name] = values
    return message


def write_night(night_id):
    """Write kafka/messages/raw-signals/<night_id>.jsonl, one raw-signals message per line.

    Returns the path and the number of minutes written.
    """
    night = _night_info(night_id)
    patient_id = DEMO_PATIENTS.get(night_id, night["patient_id"])
    data = np.load(CLEAN / "signals" / f"{night_id}.npz")
    minutes = math.ceil(len(data["spo2"]) / (60 * SIGNALS["spo2"]))

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{night_id}.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for m in range(minutes):
            minute_signals = {name: data[name][m * 60 * hz:(m + 1) * 60 * hz]
                              for name, hz in SIGNALS.items()}
            sent_at = (NIGHT_START + timedelta(minutes=m)).isoformat()
            message = build_raw_signals_message(night_id, patient_id, night["source"], m,
                                                minute_signals, m == minutes - 1, sent_at)
            f.write(json.dumps(message, separators=(",", ":"), allow_nan=False) + "\n")
    return path, minutes


def _splits():
    return json.loads((CLEAN / "splits.json").read_text(encoding="utf-8"))


def _night_info(night_id):
    for night in _splits():
        if night["night_id"] == night_id:
            return night
    raise KeyError(f"{night_id} is not in data/clean/splits.json")


# ---------------------------------------------------------------- 2. alerts


def build_alert_message(patient_id, night_id, minute, spo2_min):
    """Topic alerts, sent right away when SpO2 < 80 %."""
    spo2_min = float(spo2_min)
    if not 0 <= spo2_min < ALERT_THRESHOLD:
        raise ValueError(f"spo2_min must be 0 <= x < {ALERT_THRESHOLD:g}, not {spo2_min}")

    return {
        "patient_id": patient_id,          # Kafka key
        "night_id": night_id,
        "minute": int(minute),
        "spo2_min": round(spo2_min, 1),    # lowest SpO2 of that minute, %
        "threshold": ALERT_THRESHOLD,
        "detected_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    }


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
                               kwh=None, gco2=None, deadline_met=None,
                               llm_summary=None, llm_model=None, llm_gco2=None):
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
        "llm_summary": llm_summary,        # 2 sentences from the local LLM (ADR 0009), None = no summary
        "llm_model": llm_model,
        "llm_gco2": llm_gco2,
    }


# ---------------------------------------------------------------- 5. carbon-signal


def build_carbon_signal_message(region, intensity_g_per_kwh, mode):
    """Topic carbon-signal, the current carbon mode (low_carbon | high_carbon)."""
    if region not in REGIONS:
        raise ValueError(f"region must be one of {REGIONS}, not {region!r}")
    if mode not in CARBON_MODES:
        raise ValueError(f"mode must be one of {CARBON_MODES}, not {mode!r}")
    if float(intensity_g_per_kwh) < 0:
        raise ValueError(f"carbon intensity must be >= 0, not {intensity_g_per_kwh}")

    return {
        "region": region,                  # Kafka key
        "carbon_intensity": round(float(intensity_g_per_kwh), 1),   # gCO2/kWh
        "mode": mode,
        "sent_at": _now(),
    }


# ---------------------------------------------------------------- main


def main():
    """Write all nights from data/clean/splits.json to kafka/messages/raw-signals/."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("nights", nargs="*", help="night ids, e.g. ucddb025 (default: all)")
    parser.add_argument("--split", choices=("train", "demo", "test"),
                        help="only the nights of this split")
    args = parser.parse_args()

    nights = [n["night_id"] for n in _splits()
              if (not args.nights or n["night_id"] in args.nights)
              and (not args.split or n["split"] == args.split)]
    unknown = set(args.nights) - set(nights) if not args.split else set()
    if unknown:
        parser.error(f"unknown night(s): {', '.join(sorted(unknown))}")

    total = 0
    for night_id in nights:
        path, minutes = write_night(night_id)
        total += minutes
        print(f"{night_id:9s} {minutes:4d} minutes -> {path.relative_to(DATA.parent).as_posix()}")
    print(f"{len(nights)} nights, {total} messages")


if __name__ == "__main__":
    main()
