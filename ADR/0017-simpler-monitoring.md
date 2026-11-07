# ADR 0017: Simpler monitoring

- **Date:** 27.10.2026
- **Status:** Accepted
- **Source:** `diagrams/27.10_B_component flowchart diagram_v2_update.mmd`
- **Use cases:** UC7

## Context
v1 had many exporters. We have about 25 hours for the whole project.

## Decision
All 6 microservices expose HTTP `/metrics`; plus the Kafka exporter. Grafana shows health, latency, Kafka lag, pods, model used and CO₂. PostgreSQL exporter and extra Kubernetes metrics are removed. Supersedes ADR 0004.

## Alternatives
Keep all exporters.

## Consequences
Less setup, still covers UC7.
