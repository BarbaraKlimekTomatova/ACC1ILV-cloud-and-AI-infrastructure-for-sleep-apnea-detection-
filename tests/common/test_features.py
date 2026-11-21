"""Tests for features.py:  pytest  (settings in pytest.ini)"""


import numpy as np

import features as F

RNG = np.random.default_rng(0)


def breathing(minutes, amp=1.0, rate_hz=0.25):
    t = np.arange(minutes * 240) / 4
    return (amp * np.sin(2 * np.pi * rate_hz * t)).astype(np.float32)


def night(minutes=10, amp=1.0):
    return {"spo2": np.full(minutes * 60, 96.0, np.float32),
            "flow": breathing(minutes, amp), "thorax": breathing(minutes, amp),
            "abdomen": breathing(minutes, amp)}


def test_shape_and_no_nan():
    X = F.night_features(night(10))
    assert X.shape == (10, len(F.FEATURES))
    assert not np.isnan(X).any()


def test_same_features_for_other_units():
    # UCDDB and Apnea-ECG use different units: breathing features must not care
    a = F.night_features(night(8, amp=1.0))
    b = F.night_features(night(8, amp=20.0))
    cols = [i for i, f in enumerate(F.FEATURES) if "amp_ratio" in f or "s_below" in f]
    assert np.allclose(a[:, cols], b[:, cols], atol=1e-3)


def test_flat_breathing_is_seen_as_apnea_like():
    s = night(8)
    s["flow"][7 * 240: 7 * 240 + 120] = 0          # 30 s without airflow in minute 7
    X = F.night_features(s)
    flat = X[:, F.FEATURES.index("flow_s_below_10")]
    assert flat[7] >= 20 and flat[3] == 0


def test_desaturation_is_measured_against_baseline():
    s = night(8)
    s["spo2"][7 * 60: 7 * 60 + 30] = 91.0          # 5 % below the baseline of 96 %
    row = F.night_features(s)[7]
    assert row[F.FEATURES.index("spo2_drop")] >= 4.9
    assert row[F.FEATURES.index("spo2_s_below_3")] == 30


def test_missing_spo2_minute_does_not_break():
    s = night(5)
    s["spo2"][2 * 60: 3 * 60] = np.nan
    X = F.night_features(s)
    assert not np.isnan(X).any()
    assert X[2, F.FEATURES.index("spo2_missing")] == 1.0
