# ADR 0023: AI model trained offline and loaded from a file

- **Date:** 30.10.2026
- **Status:** Accepted
- **Source:** project summary and diagrams from 30.10 (`diagrams/30.10_B_*`)
- **Use cases:** UC2

## Context
Training inside the running service would be slow and use energy all the time.

## Decision
A training script trains the scikit-learn model, prints F1 and CO₂ and saves `models/model.joblib`. The apnea-detector loads it from `MODEL_PATH`. First by hand, later in CI with an F1 check.

## Alternatives
Train inside the service.

## Consequences
Fast start of the service; the model can be swapped without code changes.
