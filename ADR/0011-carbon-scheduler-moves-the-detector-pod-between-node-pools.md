# ADR 0011: Carbon-scheduler moves the detector pod between node pools

- **Date:** 27.10.2026
- **Status:** Accepted
- **Source:** `diagrams/27.10_B_component flowchart diagram_v2_update.mmd`
- **Use cases:** UC5

## Context
We want to show that work can move to a region with cleaner electricity.

## Decision
Nodes are labelled AT, NO and PL (simulated regions). The carbon-scheduler uses the Kubernetes API to move the apnea-detector pod to the cleanest one. It can also delay the analysis.

## Alternatives
Only switch the model: less to show.

## Consequences
Shows carbon-aware placement. The regions are simulated, not real.
