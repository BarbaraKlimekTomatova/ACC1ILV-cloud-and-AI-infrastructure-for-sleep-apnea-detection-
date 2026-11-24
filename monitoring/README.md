# Monitoring (UC6)

Prometheus reads `/metrics` of the services every 15 s, Grafana shows the dashboards, the alert rules warn the team
([UC6](../diagrams/sequences/22.11_B_UC6-monitor-system-and-footprint_v1.md), [ADR 0006](../ADR/0006-monitoring-system-and-ai-behaviour.md)).

```
monitoring/
  prometheus/rules/ai-and-carbon.yml        recording rules + UC6 A1 alerts (Barbara)
  prometheus/tests/ai-and-carbon.test.yml   promtool unit tests of the rules
  grafana/dashboards/ai-and-carbon.json     dashboard "AI & carbon" (Barbara)
  grafana/                                  Prometheus + Grafana setup, dashboard "System health" (Aliénor, to do)
```

## Dashboard "AI & carbon"

| Row | Panels | Metrics |
| --- | --- | --- |
| AI model | model used (accurate / fast), events per hour, severity of the nights | `detector_minutes_total`, `triage_nights_total` |
| Model behaviour (UC6 A1) | average confidence now vs last week, minutes with confidence < 0.7, share of event minutes now vs last week | `detector_confidence`, `detector_minutes_total` |
| Carbon | gCO₂ per night, gCO₂ per LLM summary, carbon mode, detector paused, CO₂ per hour, carbon intensity per region | `detector_gco2_total`, `triage_llm_gco2_total`, `carbon_high_mode`, `detector_paused`, `carbon_intensity` |

The dashboard has a variable `datasource`, so it works with any Prometheus data source in Grafana.

## Alert rules

| Alert | When | Use case |
| --- | --- | --- |
| `ApneaEventShareDrift` | the share of event minutes (6 h) changed by more than 50 % against the same time last week, for 30 min | UC6 A1 |
| `ModelConfidenceDrift` | the average confidence of a model (6 h) moved by more than 0.1 against last week, for 30 min | UC6 A1 |
| `ModelLowConfidence` | more than 30 % of the minutes of a model (1 h) have confidence below 0.7, for 15 min | UC6 A1 |
| `DetectorPausedLong` | the detector waits for low carbon for more than 2 h, so the 08:00 deadline is in danger | UC5 |

Drift is only a sign. The team checks the data and then starts a retraining with `triggered_by = drift` (UC7).
The A2 rules (service down, Kafka lag, deadline missed) belong to "System health".

## How to load it

Prometheus:
```yaml
rule_files:
  - /etc/prometheus/rules/*.yml
```
Grafana: put `grafana/dashboards/` into a dashboard provider (`/etc/grafana/provisioning/dashboards`) or import the JSON by hand.

## Tests

```
promtool check rules monitoring/prometheus/rules/ai-and-carbon.yml
promtool test rules monitoring/prometheus/tests/ai-and-carbon.test.yml
pytest tests/monitoring
```
`tests/monitoring` checks that every metric in the rules and in the dashboard is really exported by one of our services.
The GitHub Actions workflow `monitoring.yml` runs all three.
