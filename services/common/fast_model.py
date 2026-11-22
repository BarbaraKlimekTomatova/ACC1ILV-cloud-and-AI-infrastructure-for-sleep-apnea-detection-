# Fast model for high_carbon (UC2, UC5, ADR 0003). Owner: Aliénor.
#
# SKELETON – only the plan and the empty predict() at the end, no logic yet.
#
# Why
#   In high_carbon, close to the 08:00 deadline, the apnea-detector must still finish the night,
#   but with as little energy as possible. The accurate model (gradient boosting, model-trainer)
#   is too expensive then. The fast model is a simple RULE: no training, no scikit-learn,
#   a few comparisons per minute.
#
# TODO
#   1. Input: the features of one minute, the dict that NightFeatures.add_minute() in
#      services/common/features.py returns (42 values, e.g. the SpO2 drop below the baseline,
#      the flow amplitude ratio, the seconds below 70 % / 10 % of normal breathing, and the
#      same values of the previous minute as prev_*).
#   2. Rule: an event when SpO2 drops by >= 3 % below the baseline (the AASM hypopnea rule),
#      in this minute or the previous one (SpO2 falls 20-40 s after the breathing stops).
#      Optional: also an event when the airflow is almost flat (apnea) even without a drop.
#   3. Output, the same as the detector expects from every model:
#      event "apnea_or_hypopnea" or "normal", plus a probability between 0 and 1
#      (e.g. how far the drop is above the 3 % limit). The fast model cannot tell apnea from
#      hypopnea; ahi-triage already handles that (apnea_count / hypopnea_count = null).
#   4. Tests in tests/common/test_fast_model.py: a minute with a 4 % drop -> event,
#      1 % -> normal, missing SpO2 (NaN) -> normal, the drop only in prev_* -> event.
#   5. F1 on the held-out Apnea-ECG nights (split = test in data/clean/splits.json), the same
#      way as evaluate() in services/model-trainer/train.py, so it can be compared with the
#      accurate model (F1 0.906). It should pass the F1 gate (>= 0.80).
#   6. Model comparison (separate task, same owner): F1, run time per night and gCO2 of the accurate model
#      and of this rule, plus the AHI of the 5 demo nights. This is the sustainability
#      trade-off for the presentation (ADR 0003, 0010).
#   7. Nothing to wire: the detector and the notebook already call predict(). As soon as it
#      returns a result instead of NotImplementedError, the detector uses it in its FAST mode.
#   8. Run notebooks/pipeline_walkthrough.ipynb again: parts 4 and 5 then show the rule
#      (F1, confusion matrix, the high_carbon scenario) instead of "not ready yet".
#   9. README: switch "Fast model as a rule" and "Model comparison script" to done.
#
# Already wired in (do not rename):
#   * the apnea-detector calls predict() in its FAST mode (detector.py, load_fast_model()).
#     While predict() raises NotImplementedError, the detector uses the accurate model instead.
#   * notebooks/pipeline_walkthrough.ipynb uses predict() in part 4 and 5 the same way.

VERSION = "rule-v1"          # goes into apnea-events.model_version and results.model_version


def predict(features):
    """Features of one minute (the dict from NightFeatures.add_minute) -> (event, probability).

    event:       "apnea_or_hypopnea" or "normal"
    probability: a number between 0 and 1
    """
    # TODO steps 1-3 above
    raise NotImplementedError("fast_model.py is still a skeleton (owner: Aliénor)")
