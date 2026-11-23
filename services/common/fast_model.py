# Fast model for high_carbon (UC2, UC5, ADR 0003). Owner: Aliénor.
#
# Why
#   In high_carbon, close to the 08:00 deadline, the apnea-detector must still finish the night,
#   but with as little energy as possible. The accurate model (gradient boosting, model-trainer)
#   is too expensive then. The fast model is a simple RULE: no training, no scikit-learn,
#   two comparisons per minute.
#
# Rule (AASM hypopnea rule, simplified)
#   event when SpO2 drops by >= 3 % below the patient's own baseline in THIS minute or in the
#   PREVIOUS one (SpO2 falls 20-40 s after the breathing stops, so the drop often comes late).
#   The baseline and the drop come from services/common/features.py (spo2_drop, prev_spo2_drop).
#   The rule cannot tell apnea from hypopnea; ahi-triage already handles that
#   (apnea_count / hypopnea_count = null).
#
# Quality on the held-out Apnea-ECG nights (split = test, 3875 minutes, same as train.py evaluate()):
#   F1 0.832   precision 0.714   recall 0.996      (accurate model: F1 0.906; F1 gate: >= 0.80)
#   An extra "flat airflow" condition (flow_s_below_10 >= 10 s) did not change the F1, so it is not used.
#
# Used by (do not rename):
#   * the apnea-detector in its FAST mode (detector.py, load_fast_model() / RuleModel)
#   * notebooks/pipeline_walkthrough.ipynb, part 4 and 5
#   Tests: tests/common/test_fast_model.py

import math

VERSION = "rule-v1"          # goes into apnea-events.model_version and results.model_version
DROP_LIMIT = 3.0             # % below the SpO2 baseline
FULL_CONFIDENCE_AT = 3.0     # confidence reaches 1.0 this far (in %) away from the limit

EVENT, NORMAL = "apnea_or_hypopnea", "normal"


def _drop(minute, key):
    """SpO2 drop in %, 0 if it is missing or NaN (no SpO2 = no evidence of an event)."""
    v = minute.get(key)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(v) else max(0.0, v)


def predict(minute):
    """Features of one minute (the dict from NightFeatures.add_minute) -> (event, confidence).

    event:       "apnea_or_hypopnea" or "normal"
    confidence:  0.5 .. 1.0, how sure the rule is about THAT event: 0.5 right at the 3 % limit,
                 1.0 when the drop is 3 % or more away from it (0 % drop -> normal 1.0,
                 6 % drop -> event 1.0). Same meaning as "probability" in apnea-events.
    """
    drop = max(_drop(minute, "spo2_drop"), _drop(minute, "prev_spo2_drop"))
    distance = min(1.0, abs(drop - DROP_LIMIT) / FULL_CONFIDENCE_AT)
    confidence = round(0.5 + 0.5 * distance, 3)
    return (EVENT if drop >= DROP_LIMIT else NORMAL), confidence
