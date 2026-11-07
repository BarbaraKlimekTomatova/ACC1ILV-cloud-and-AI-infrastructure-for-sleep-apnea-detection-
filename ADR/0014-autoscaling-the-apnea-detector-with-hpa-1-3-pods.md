# ADR 0014: Autoscaling the apnea-detector with HPA (1–3 pods)

- **Date:** 27.10.2026
- **Status:** Accepted
- **Source:** `diagrams/27.10_B_component flowchart diagram_v2_update.mmd`
- **Use cases:** UC6

## Context
Many nights can arrive at once (burst).

## Decision
A Horizontal Pod Autoscaler scales the apnea-detector from 1 to 3 pods.

## Alternatives
Fixed number of pods: wastes resources or is too slow.

## Consequences
Shows scaling. `raw-signals` needs at least 3 partitions.
