"""Tests of the fast model rule (services/common/fast_model.py)."""

import math

import fast_model as FM
import features as F


def minute(drop=0.0, prev_drop=0.0):
    row = {f: 0.0 for f in F.FEATURES}
    row["spo2_drop"], row["prev_spo2_drop"] = drop, prev_drop
    return row


def test_4_percent_drop_is_an_event():
    event, conf = FM.predict(minute(4.0))
    assert event == "apnea_or_hypopnea" and 0.5 < conf <= 1.0


def test_1_percent_drop_is_normal():
    event, conf = FM.predict(minute(1.0))
    assert event == "normal" and 0.5 < conf <= 1.0


def test_exactly_3_percent_is_an_event_with_low_confidence():
    assert FM.predict(minute(3.0)) == ("apnea_or_hypopnea", 0.5)


def test_missing_spo2_is_normal():
    assert FM.predict(minute(math.nan, math.nan))[0] == "normal"
    assert FM.predict({})[0] == "normal"


def test_drop_only_in_the_previous_minute_is_an_event():
    assert FM.predict(minute(0.0, 5.0))[0] == "apnea_or_hypopnea"


def test_confidence_grows_with_the_distance_to_the_limit():
    assert FM.predict(minute(6.0))[1] == 1.0 == FM.predict(minute(0.0))[1]
    assert FM.predict(minute(3.5))[1] < FM.predict(minute(5.0))[1]


def test_detector_uses_the_rule():
    import detector as D
    fast = D.load_fast_model()
    assert fast is not None and fast.version == FM.VERSION == "rule-v1"
    assert fast.predict(minute(4.0))[0] == "apnea_or_hypopnea"


def test_works_on_real_features():
    import numpy as np
    nf = F.NightFeatures()
    for _ in range(3):
        row = nf.add_minute(np.full(60, 97, np.float32), np.sin(np.arange(240)), np.sin(np.arange(240)),
                            np.sin(np.arange(240)))
    assert FM.predict(row)[0] == "normal"
    low = np.full(60, 90, np.float32)
    assert FM.predict(nf.add_minute(low, np.sin(np.arange(240)), np.sin(np.arange(240)),
                                    np.sin(np.arange(240))))[0] == "apnea_or_hypopnea"
