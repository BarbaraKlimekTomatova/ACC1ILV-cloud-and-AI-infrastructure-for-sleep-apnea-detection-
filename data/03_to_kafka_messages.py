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


def build_apnea_event_message(patient_id, night_id, minute, event, probability,
                              model, carbon_mode, is_last):
    """Topic apnea-events, the detector's answer for one minute."""
    # TODO: Barbara
    raise NotImplementedError


# ---------------------------------------------------------------- 4. night-results


def build_night_result_message(patient_id, night_id, ahi, severity):
    """Topic night-results, AHI and severity of one finished night."""
    # TODO: Barbara
    raise NotImplementedError


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
