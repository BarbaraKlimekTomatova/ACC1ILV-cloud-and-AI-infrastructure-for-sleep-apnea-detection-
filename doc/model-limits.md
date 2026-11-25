# Known limits of the model

For the presentation: what our AHI means, where it differs from a sleep lab and what the carbon mode changes.
Numbers from `python scripts/ahi_vs_clinical.py` (the 5 demo nights, same feature code and models as the live apnea-detector).

## AHI of the 5 demo nights

| Night | Recording (h) | Sleep (h) | Clinical AHI | Labels per minute | Accurate model | Fast rule | Severity: clinical / accurate / fast |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ucddb010 | 7.5 | 7.0 | 33.4 | 20.4 | 21.5 | 45.6 | severe / **moderate** / severe |
| ucddb013 | 6.8 | 4.1 | 15.7 | 10.5 | 12.0 | 32.3 | moderate / **mild** / **severe** |
| ucddb017 | 6.6 | 5.7 | 12.0 | 9.9 | 11.4 | 29.5 | mild / mild / **moderate** |
| ucddb018 | 6.8 | 4.1 | 2.2 | 1.3 | 0.6 | 1.5 | normal / normal / normal |
| ucddb025 | 5.9 | 4.6 | 94.1 | 52.7 | 53.7 | 55.3 | severe / severe / severe |

- **Clinical AHI:** scored apnea and hypopnea events of the sleep lab / hours of sleep.
- **Labels per minute:** minutes with an event in the labels / hours of recording. This is the best a perfect per-minute model can reach.
- **Accurate model** (low_carbon) and **fast rule** (high_carbon): minutes the model calls an event / hours of recording.

## 1. Our AHI is lower than the clinical AHI

The accurate model is close to the labels per minute (21.5 vs 20.4, 12.0 vs 10.5, 53.7 vs 52.7), so the gap to the
clinical AHI comes from how we count, not from the model:

1. **One event per minute at most.** We label minutes, not events. Two short apneas in one minute count as one,
   so our AHI can never be higher than 60. ucddb025 has 94 events per hour of sleep, we see 54.
2. **Hours of recording, not hours of sleep.** A home device does not measure sleep (no EEG), so we divide by the
   whole night. Wake time makes the AHI smaller: ucddb013 slept only 4.1 of 6.8 hours.
3. **No arousals.** The clinical hypopnea rule also counts a 30 % airflow drop with an EEG arousal. We only see the
   3 % SpO₂ drop, so some hypopneas are missed.

Effect: the severity can be one class too low near a limit (ucddb010 moderate instead of severe, ucddb013 mild
instead of moderate). Our result is a **screening for the doctor**, not a diagnosis. The doctor confirms it in the
sleep lab (UC4).

## 2. The result depends on the carbon mode

| | Accurate model (low_carbon) | Fast rule `rule-v1` (high_carbon) |
| --- | --- | --- |
| F1 on the held-out Apnea-ECG nights (3875 minutes) | 0.906 | 0.832 |
| Precision / recall | 0.850 / 0.971 | 0.714 / 0.996 |
| Apnea vs hypopnea | yes | no (`apnea_count`, `hypopnea_count` = null) |
| CPU time to classify one night (features not included) | about 50 ms | below 1 ms |

- The rule finds almost every event (recall 0.996), but also calls many normal minutes an event (precision 0.714).
  So it **overestimates** the AHI: ucddb013 moderate → severe, ucddb017 mild → moderate.
- For triage this is the safe direction: a patient is sent to the doctor too early, not too late.
- `results.model` and `results.carbon_mode` store which model ran, so the doctor sees it. A night analysed in high
  carbon can be analysed again with the accurate model later.
- In high carbon far from 08:00 the detector waits instead (ADR 0003), so most nights still get the accurate model.

## 3. Other limits

- **Small data.** 20 training nights from one sleep lab (UCDDB), test on 8 Apnea-ECG nights. The Apnea-ECG
  experts did not split apnea and hypopnea, so this split is not tested.
- **Labels from two datasets.** UCDDB has scored events, Apnea-ECG has one label per minute. We turn the UCDDB events
  into minute labels, which is what makes the per-minute counting above.
- **Signal quality.** A sensor drop-out (SpO₂ = NaN) counts as no event. A long drop-out lowers the AHI.
- **CO₂ is an estimate.** The detector uses CPU time × power × carbon intensity (simulated for AT / NO / PL). Only the
  training is measured with CodeCarbon (ADR 0010, to do).
- **Confidence is not calibrated.** `detector_confidence` is the probability of the model (rule: 0.5–1.0 by distance
  to the 3 % limit). It is good for drift (UC6), not as a medical certainty.
