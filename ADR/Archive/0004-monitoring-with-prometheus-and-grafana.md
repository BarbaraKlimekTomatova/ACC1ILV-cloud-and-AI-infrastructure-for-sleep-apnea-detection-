# ADR 0004: Monitoring with Prometheus and Grafana

- **Date:** 24.10.2026
- **Status:** Superseded by ADR 0017
- **Source:** `diagrams/24.10_A_component-diagram_v1.mmd`
- **Use cases:** UC7

## Context
The team must see if the system is healthy: services, Kafka, database and cluster.

## Decision
Prometheus collects `/metrics` from all services, plus the Kafka exporter, the PostgreSQL exporter and Kubernetes metrics. Grafana shows one dashboard.

## Alternatives
Only logs: no graphs, hard to show in a demo.

## Consequences
We see everything in one place. Many exporters to set up.
