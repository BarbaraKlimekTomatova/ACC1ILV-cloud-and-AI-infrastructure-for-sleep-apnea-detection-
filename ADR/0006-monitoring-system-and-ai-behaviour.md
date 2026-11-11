# ADR 0006: Monitoring of system health and AI behaviour

- **Status:** Accepted
- **Date:** 09.11.2026
- **Use cases:** UC6

## Context
We must see that the system works and that the SLOs hold. Because an AI model makes medical decisions, we also need to see if the model still behaves well, and how much CO₂ the system uses.

## Options
1. **Only logs:** cheap, but no overview and no warnings.
2. **Only system metrics** (CPU, latency, pods): shows if the system runs, but not if the AI is still good.
3. **System metrics and AI metrics** in Prometheus and Grafana, with warning rules.

## Decision
We use option 3. All services expose `/metrics`, plus the Kafka exporter.
- **System:** latency, Kafka lag (nights waiting), pods, alert time.
- **AI:** model and version used, confidence of the predictions, events per hour, CO₂ per night.

A rule warns the team when the AI behaviour drifts (for example, the share of nights with many events or the average confidence changes much compared to last week).

## Consequences
- We can check the SLOs and compare the carbon modes in one Grafana dashboard.
- Drift is only a warning sign. It does not prove that the model is wrong, so the team decides if a retraining (ADR 0005) is needed.
- Prometheus and Grafana also use resources; we keep few metrics and a short retention.
