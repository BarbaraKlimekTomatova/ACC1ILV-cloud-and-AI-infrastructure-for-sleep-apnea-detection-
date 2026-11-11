# ADR 0005: Model lifecycle – carbon-aware retraining

- **Status:** Accepted
- **Date:** 09.11.2026
- **Use cases:** UC7, UC2

## Context
The apnea-detector uses an AI model. Training uses much more energy than one analysis, and a bad new model could harm patients. We need a repeatable way to train, check and deploy new model versions.

## Options
1. **Train inside the running detector:** no extra parts, but it uses energy all the time and the model can change without any check.
2. **Train by hand on a laptop and copy the file:** cheap, but not repeatable and not measured.
3. **Training as a Kubernetes Job in the CI/CD pipeline, started only in a low-carbon window:** the new model is tested and versioned before use.

## Decision
We use option 3. The team starts a retraining (UC7). The Job waits until the carbon mode is `low_carbon`, trains the model, measures F1 and CO₂ (CodeCarbon) and saves a new model version. GitHub Actions uses the new version only if its F1 score is above our threshold; then it builds and deploys the detector image.

## Consequences
- Training runs at the cleanest time and its CO₂ is measured.
- A worse model never reaches the patients (F1 gate).
- Every result in the database stores the model version, so we know which model analysed which night.
- The pipeline is more complex than copying a file.
