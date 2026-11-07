# ADR 0013: Fast or accurate model, CO₂ measured with CodeCarbon

- **Date:** 27.10.2026
- **Status:** Accepted (training in ADR 0023)
- **Source:** `diagrams/27.10_B_component flowchart diagram_v2_update.mmd`
- **Use cases:** UC2, UC5

## Context
Better AI uses more energy. We want to show the trade-off.

## Decision
The apnea-detector has a fast model and an accurate model. The carbon mode decides which one runs. CodeCarbon measures the CO₂.

## Alternatives
One model only: nothing to optimise.

## Consequences
We can compare accuracy and CO₂ in the demo. Two models to keep.
