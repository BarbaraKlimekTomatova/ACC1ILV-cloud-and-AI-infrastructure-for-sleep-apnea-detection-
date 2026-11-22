# ADR 0008: One feature code for training and live analysis

- **Status:** Accepted
- **Date:** 22.11.2026
- **Use cases:** UC2, UC7

## Context
The model is trained by the model-trainer on whole nights from files, but used by the apnea-detector on one
minute after the other from Kafka. If the two services compute the features in different ways, the model
sees other numbers live than in training ("training/serving skew") and becomes worse without anyone noticing.
Live, the detector also cannot look into the future: it only has the current and the earlier minutes.

## Options
1. **Separate feature code in each service:** each service stays on its own, but two copies drift apart.
2. **A feature store** (e.g. Feast) that both services read: standard in big systems, but one more component
   to run and power for a project with 42 features.
3. **One shared Python module** that both services import.

## Decision
We use option 3: `services/common/features.py` with `NightFeatures.add_minute()`.
- The detector calls it for every minute it reads from `raw-signals`.
- The model-trainer replays every night minute by minute through the same class (`night_features()`).
- The features are causal: baselines use only the current and the last 5 minutes, like live.
- The model file stores the list of feature names. The detector refuses a model whose features do not match.

## Consequences
- Training and live use exactly the same numbers. Tests in `tests/common/` check the features once for both.
- Both Docker images copy `services/common/`, so a change there means rebuilding both images (and retraining).
- The services are less independent: the shared module is a contract between them, like a Kafka schema.
- **Sustainability trade-off:** no feature store to run, and the features are computed only once per minute.
