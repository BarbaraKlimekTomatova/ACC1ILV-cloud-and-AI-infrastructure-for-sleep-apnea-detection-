"""Step 2: clean the nights and separate signals from labels.

Usage:
    python data/02_clean.py

Input:   data/raw/<night>.npz          (from 01_download.py)
Output:  data/clean/signals/<night>.npz   only what the home device measures
         data/clean/labels.csv            the answers, one row per minute (training only)
         data/clean/splits.json           which night is train / demo / test

What "clean" means here (only small, safe fixes, no feature engineering):
  1. SpO2 gaps of up to 10 seconds are filled by a straight line between the
     neighbours (a short sensor drop-out). Longer gaps stay NaN, because
     inventing minutes of oxygen values would be lying.
  2. Each minute gets a quality flag `usable` in labels.csv:
       0 if more than half of its SpO2 seconds are missing, or
       0 if flow, thorax and abdomen are all flat (sensor off / disconnected),
       1 otherwise.
     Training skips unusable minutes; the live system still receives them.
  3. Each minute gets an event label `event` in labels.csv (3 classes):
       UCDDB:     "apnea" or "hypopnea" if a scored event of that type touches
                  the minute (same rule as `apnea` in 01_download.py), else
                  "normal". If both touch the same minute, "apnea" wins.
       Apnea-ECG: the experts only scored apnea yes/no per minute, without
                  the type, so an "A" minute becomes "apnea_or_hypopnea".
       No label (-1) -> "unknown".
     The old 0/1 column `apnea` stays, so the binary F1 on Apnea-ECG still works.
  4. Signals and labels go to different files. The signals are what Kafka
     will carry later (step 3). The labels never go to Kafka, they are only
     used to train and to test the model.

What we do NOT do here: no normalisation, no filtering, no features.
That happens inside the apnea-detector, so training and live use run the
same code on the same kind of input.

Split (by person, so the model is never tested on someone it has seen):
  UCDDB:     one night = one person. 5 nights spread from mild to severe AHI
             -> demo (the live demo), the other 20 -> train.
  Apnea-ECG: 8 other people -> test (held out, used only for the final F1).
"""

import csv
import json
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent
RAW = DATA / "raw"
CLEAN = DATA / "clean"
SIGNALS_DIR = CLEAN / "signals"

SIGNALS = {"spo2": 1, "flow": 4, "thorax": 4, "abdomen": 4}   # Hz
MAX_SPO2_GAP_S = 10        # fill SpO2 gaps up to this length
MAX_MISSING_SPO2 = 0.5     # minute unusable above this missing fraction
FLAT_STD = 1e-3            # breathing signal "flat" below this std in a minute
N_DEMO = 5


# ---------------------------------------------------------------- cleaning


def fill_short_gaps(x, max_gap):
    """Fill NaN runs of length <= max_gap by linear interpolation."""
    x = x.astype(np.float32)
    nan = np.isnan(x)
    if not nan.any() or nan.all():
        return x
    idx = np.arange(x.size)
    filled = np.interp(idx, idx[~nan], x[~nan]).astype(np.float32)
    # find the runs of NaN and keep only the short ones filled
    edges = np.diff(np.concatenate([[0], nan.astype(np.int8), [0]]))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
    for s, e in zip(starts, ends):
        inside = s > 0 and e < x.size          # need a neighbour on both sides
        if inside and e - s <= max_gap:
            x[s:e] = filled[s:e]
    return x


def usable_minutes(sig, minutes):
    """1 = good minute for training, 0 = too much missing / sensor off."""
    spo2 = sig["spo2"].reshape(minutes, 60)
    missing = np.isnan(spo2).mean(axis=1)
    flat = np.ones(minutes, bool)
    for s in ("flow", "thorax", "abdomen"):
        flat &= sig[s].reshape(minutes, 240).std(axis=1) < FLAT_STD
    return ((missing <= MAX_MISSING_SPO2) & ~flat).astype(np.int8)


# ---------------------------------------------------------------- labels / split


def source_of(night):
    return "ucddb" if night.startswith("ucddb") else "apnea-ecg"


def patient_of(night):
    # Apnea-ECG night a01r belongs to person a01; UCDDB: one night per person.
    return night.rstrip("r") if source_of(night) == "apnea-ecg" else night


EVENT_CLASSES = ("normal", "hypopnea", "apnea")   # for the 3-class model


def minute_events(d, minutes):
    """One event label per minute: normal / hypopnea / apnea (see point 3)."""
    if "event_type" not in d.files:                      # Apnea-ECG
        return np.array(["unknown" if a < 0 else "apnea_or_hypopnea" if a == 1
                         else "normal" for a in d["apnea"]], dtype="U17")
    event = np.full(minutes, "normal", dtype="U17")
    # hypopnea first, apnea second, so apnea wins in a minute with both
    for prefix, name in (("HYP", "hypopnea"), ("APNEA", "apnea")):
        for on, dur, typ in zip(d["event_onset_s"], d["event_duration_s"], d["event_type"]):
            if str(typ).startswith(prefix):
                event[int(on // 60): int((on + dur) // 60) + 1] = name
    return event


def event_counts(d):
    """Number of scored apnea and hypopnea events of the night (UCDDB only)."""
    if "event_type" not in d.files:
        return None, None
    types = [str(t) for t in d["event_type"]]
    return (sum(t.startswith("APNEA") for t in types),
            sum(t.startswith("HYP") for t in types))


def ahi(d):
    """Apnea-hypopnea events per hour of sleep (UCDDB only, needs scored events)."""
    if "event_type" not in d.files:
        return None
    n = sum(t.startswith(("APNEA", "HYP")) for t in d["event_type"])
    sleep_h = np.isin(d["sleep_stage"], [1, 2, 3, 4, 5]).sum() / 60
    return round(n / (sleep_h or len(d["sleep_stage"]) / 60), 1)


def make_splits(nights):
    """Test = Apnea-ECG. Demo = 5 UCDDB nights spread over the AHI range."""
    ucd = sorted((n for n in nights if n["source"] == "ucddb"), key=lambda n: n["ahi"])
    pick = np.linspace(0, len(ucd) - 1, min(N_DEMO, len(ucd))).round().astype(int)
    demo = {ucd[i]["night_id"] for i in pick}
    for n in nights:
        n["split"] = ("test" if n["source"] == "apnea-ecg"
                      else "demo" if n["night_id"] in demo else "train")
    return nights


# ---------------------------------------------------------------- main


def main():
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    nights, rows = [], []
    for path in sorted(RAW.glob("*.npz")):
        night = path.stem
        d = np.load(path)
        minutes = len(d["apnea"])

        sig = {s: d[s].astype(np.float32) for s in SIGNALS}
        sig["spo2"] = fill_short_gaps(sig["spo2"], MAX_SPO2_GAP_S)
        usable = usable_minutes(sig, minutes)
        event = minute_events(d, minutes)
        apnea_n, hypopnea_n = event_counts(d)

        np.savez_compressed(SIGNALS_DIR / f"{night}.npz",
                            **{s: x.astype(np.float16) for s, x in sig.items()})

        for m in range(minutes):
            rows.append([night, patient_of(night), source_of(night), m,
                         int(d["apnea"][m]), event[m],
                         int(d["sleep_stage"][m]), int(usable[m])])

        nights.append({"night_id": night, "patient_id": patient_of(night),
                       "source": source_of(night), "minutes": minutes,
                       "usable_minutes": int(usable.sum()),
                       "apnea_minutes": int((d["apnea"] == 1).sum()),
                       "minutes_by_event": {e: int((event == e).sum())
                                            for e in np.unique(event)},
                       "apnea_count": apnea_n, "hypopnea_count": hypopnea_n,
                       "ahi": ahi(d)})
        print(f"{night}: {minutes} min, {int(usable.sum())} usable, "
              f"{100 * np.isnan(sig['spo2']).mean():.1f}% SpO2 still missing")

    with open(CLEAN / "labels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["night_id", "patient_id", "source", "minute",
                    "apnea", "event", "sleep_stage", "usable"])
        w.writerows(rows)

    nights = make_splits(nights)
    (CLEAN / "splits.json").write_text(json.dumps(nights, indent=2))

    count = {s: sum(n["split"] == s for n in nights) for s in ("train", "demo", "test")}
    print(f"done: {len(nights)} nights -> {CLEAN}  {count}")
    print("demo nights:", [n["night_id"] for n in nights if n["split"] == "demo"])


if __name__ == "__main__":
    main()
