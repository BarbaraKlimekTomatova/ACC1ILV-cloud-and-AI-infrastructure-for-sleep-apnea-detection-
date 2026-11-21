"""Features per minute for the apnea detector.

The SAME code runs in training (model-trainer) and live (apnea-detector),
so the model always sees the same kind of numbers.

Input of one minute (exactly what a raw-signals message carries):
    spo2      60 values, 1 Hz, in %, NaN = sensor drop-out
    flow      240 values, 4 Hz, oronasal airflow, raw device units
    thorax    240 values, 4 Hz, chest breathing movement, raw units
    abdomen   240 values, 4 Hz, belly breathing movement, raw units

Why the features look like this
  * The devices of our two datasets use different units (UCDDB flow is about
    20x larger than Apnea-ECG flow). So breathing features are never absolute:
    they are a ratio to the patient's OWN normal breathing of the last minutes.
  * The clinical rules (AASM) also work like this:
      apnea     = airflow drops by >= 90 % for >= 10 s
      hypopnea  = airflow drops by >= 30 % for >= 10 s AND SpO2 falls by >= 3 %
    so we measure how long the amplitude stays below 10 % and below 70 % of
    normal, and how deep SpO2 falls below its baseline.
  * Live, the detector gets one minute after the other and cannot look into
    the future. So the baselines use only the current and earlier minutes
    (a "causal" rolling window). Training replays the night in the same order.
  * SpO2 falls 20-40 s AFTER the breathing stops, so a desaturation often
    shows up in the next minute. That is why we also keep the features of
    the previous minute (prev_*).

Usage
    nf = NightFeatures()                      # one per night
    row = nf.add_minute(spo2, flow, thorax, abdomen)   # dict, live
    X = night_features(npz)                   # minutes x features, training
"""

from collections import deque

import numpy as np

SPO2_HZ, BREATH_HZ = 1, 4
WINDOW_S = 10                      # breathing amplitude in 10 s windows
BASELINE_MINUTES = 5               # "normal" = the last 5 minutes
SPO2_BASELINE_PCT = 90             # SpO2 baseline = 90th percentile of the history
APNEA_RATIO, HYPOPNEA_RATIO = 0.1, 0.7
BREATHING = ("flow", "thorax", "abdomen")

# the order of the columns the model is trained on
CURRENT = [
    "spo2_mean", "spo2_min", "spo2_drop", "spo2_slope",
    "spo2_s_below_3", "spo2_s_below_4", "spo2_missing",
    *[f"{s}_{f}" for s in BREATHING
      for f in ("amp_ratio_min", "amp_ratio_mean", "s_below_10", "s_below_70")],
    "flow_breaths", "thorax_abdomen_corr",
]
FEATURES = CURRENT + [f"prev_{f}" for f in CURRENT]


def _amplitudes(x):
    """Breathing amplitude per 10 s window: 5th-95th percentile range.

    Also the per-second amplitude (over a centred 10 s window) to count how
    many seconds the breathing is flat.
    """
    x = np.nan_to_num(np.asarray(x, np.float32))
    win = WINDOW_S * BREATH_HZ
    windows = x[: len(x) // win * win].reshape(-1, win)
    per_window = np.percentile(windows, 95, axis=1) - np.percentile(windows, 5, axis=1)
    # per second: range of the 10 s around each second
    pad = np.pad(x, win // 2, mode="edge")
    idx = np.arange(0, len(x), BREATH_HZ)
    per_second = np.array([np.ptp(pad[i: i + win]) for i in idx], np.float32)
    return per_window, per_second


def _breaths(flow):
    """Breaths in this minute = upward zero crossings of the centred flow."""
    x = np.nan_to_num(np.asarray(flow, np.float32))
    x = x - np.median(x)
    up = (x[:-1] < 0) & (x[1:] >= 0)
    return float(up.sum())


def _slope(y):
    """%SpO2 per minute, NaN-safe linear fit."""
    t = np.arange(len(y))
    ok = ~np.isnan(y)
    if ok.sum() < 10:
        return 0.0
    return float(np.polyfit(t[ok], y[ok], 1)[0] * 60)


class NightFeatures:
    """Keeps the short history of one night and turns minutes into features."""

    def __init__(self):
        self.spo2_hist = deque(maxlen=BASELINE_MINUTES * 60 * SPO2_HZ)
        self.amp_hist = {s: deque(maxlen=BASELINE_MINUTES * 60 // WINDOW_S)
                         for s in BREATHING}
        self.prev = None

    def add_minute(self, spo2, flow, thorax, abdomen):
        sig = {"flow": flow, "thorax": thorax, "abdomen": abdomen}
        spo2 = np.asarray(spo2, np.float32)
        f = {}

        # ---- SpO2: depth and length of the desaturation vs. own baseline
        self.spo2_hist.extend(spo2[~np.isnan(spo2)])
        base = (np.percentile(self.spo2_hist, SPO2_BASELINE_PCT)
                if self.spo2_hist else np.nan)
        missing = float(np.isnan(spo2).mean())
        if missing < 1:
            f["spo2_mean"] = float(np.nanmean(spo2))
            f["spo2_min"] = float(np.nanmin(spo2))
        else:                                   # whole minute missing
            f["spo2_mean"] = f["spo2_min"] = float(base) if base == base else 95.0
        f["spo2_drop"] = float(max(0.0, base - f["spo2_min"])) if base == base else 0.0
        f["spo2_slope"] = _slope(spo2)
        f["spo2_s_below_3"] = float(np.nansum(spo2 < base - 3)) if base == base else 0.0
        f["spo2_s_below_4"] = float(np.nansum(spo2 < base - 4)) if base == base else 0.0
        f["spo2_missing"] = missing

        # ---- breathing: amplitude as a ratio to the last 5 minutes
        for s, x in sig.items():
            per_window, per_second = _amplitudes(x)
            hist = self.amp_hist[s]
            normal = np.median(hist) if hist else np.median(per_window)
            normal = normal if normal > 1e-6 else 1e-6
            ratio_w = per_window / normal
            ratio_s = per_second / normal
            f[f"{s}_amp_ratio_min"] = float(ratio_w.min())
            f[f"{s}_amp_ratio_mean"] = float(ratio_w.mean())
            f[f"{s}_s_below_10"] = float((ratio_s < APNEA_RATIO).sum())
            f[f"{s}_s_below_70"] = float((ratio_s < HYPOPNEA_RATIO).sum())
            hist.extend(per_window)             # update AFTER using it

        f["flow_breaths"] = _breaths(flow)
        th, ab = (np.nan_to_num(np.asarray(sig[s], np.float32)) for s in ("thorax", "abdomen"))
        f["thorax_abdomen_corr"] = (float(np.corrcoef(th, ab)[0, 1])
                                    if th.std() > 1e-6 and ab.std() > 1e-6 else 0.0)

        # ---- previous minute (desaturation comes late)
        prev = self.prev or {k: f[k] for k in CURRENT}
        row = {**{k: f[k] for k in CURRENT}, **{f"prev_{k}": prev[k] for k in CURRENT}}
        self.prev = {k: f[k] for k in CURRENT}
        return row


def to_vector(row):
    """dict -> numpy row in the fixed FEATURES order (what the model expects)."""
    return np.array([row[k] for k in FEATURES], np.float32)


def night_features(signals):
    """All minutes of one night -> array (minutes x len(FEATURES)).

    `signals` = an .npz from data/clean/signals/ (or a dict with the same keys).
    Uses NightFeatures minute by minute, exactly like the live detector.
    """
    minutes = len(signals["spo2"]) // 60
    nf = NightFeatures()
    rows = []
    for m in range(minutes):
        s1, s4 = slice(m * 60, (m + 1) * 60), slice(m * 240, (m + 1) * 240)
        rows.append(to_vector(nf.add_minute(
            signals["spo2"][s1].astype(np.float32),
            signals["flow"][s4], signals["thorax"][s4], signals["abdomen"][s4])))
    return np.vstack(rows)
