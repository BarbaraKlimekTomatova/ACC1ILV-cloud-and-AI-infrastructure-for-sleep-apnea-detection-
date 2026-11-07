# ADR 0016: Kafka with one broker

- **Date:** 27.10.2026
- **Status:** Superseded by ADR 0020
- **Source:** `diagrams/27.10_B_component flowchart diagram_v2_update.mmd`
- **Use cases:** UC1, UC2

## Context
A single broker is the simplest setup for the start.

## Decision
Kafka runs with 1 broker.

## Alternatives
3 brokers.

## Consequences
Simple, but if the broker stops, the whole pipeline stops.
