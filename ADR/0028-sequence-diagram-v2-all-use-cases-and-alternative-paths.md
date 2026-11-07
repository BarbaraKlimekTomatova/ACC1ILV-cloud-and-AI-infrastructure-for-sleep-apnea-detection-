# ADR 0028: Sequence diagram v2: all use cases and alternative paths

- **Date:** 30.10.2026
- **Status:** Accepted
- **Source:** `diagrams/30.10_B_sequence-diagram_v2.mmd`
- **Use cases:** UC1–UC7

## Context
Sequence diagram v1 (ADR 0019) shows only the happy path. The professor wants alternative paths, and UC6 (scaling) was missing.

## Decision
Sequence diagram v2 keeps Aliénor's colours and adds: `alt` for the carbon mode (low_carbon = accurate model, high_carbon = wait, close to 08:00 = fast model), `opt` for the alert (checked every minute in every mode), `opt` for the last minute of the night, `alt` for the doctor (agrees / corrects), a UC6 block (HPA 1 → 3 pods) and a pod move to a cleaner region. Names are low_carbon / high_carbon and Kafka has 3 brokers. Supersedes ADR 0019.

## Alternatives
Separate diagrams per use case (we have them as extra material, but the summary uses one).

## Consequences
One diagram covers UC1–UC7 and is the one used in the project summary.
