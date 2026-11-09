# ADR 0006: Replay PhysioNet nights in the device-simulator

- **Date:** 24.10.2026
- **Status:** Superseded by ADR 0012
- **Source:** `diagrams/24.10_A_component-diagram_v1.mmd`
- **Use cases:** UC1

## Context
We have no real home sleep devices, so we need realistic data.

## Decision
The device-simulator replays nights from PhysioNet and sends 1 frame per minute to Kafka.

## Alternatives
Write our own data generator.

## Consequences
Real medical data. We need to download and convert the PhysioNet files.
