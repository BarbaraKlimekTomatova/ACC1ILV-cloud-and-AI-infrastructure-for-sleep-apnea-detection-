# ADR 0009: Urgent alerts over ZeroMQ to a separate alert-service

- **Date:** 27.10.2026
- **Status:** Accepted (made exact in ADR 0022)
- **Source:** `diagrams/27.10_B_component flowchart diagram_v2_update.mmd`
- **Use cases:** UC3

## Context
When SpO₂ falls below 80 %, the alert must come at once. It must not wait in a queue behind normal analysis.

## Decision
The apnea-detector sends the alert directly over ZeroMQ to the alert-service, which stores it in PostgreSQL.

## Alternatives
A 4th Kafka topic for alerts: one technology less, but it shows less of what the course covers.

## Consequences
Alerts are fast and independent of Kafka. ZeroMQ is one more technology to learn.
