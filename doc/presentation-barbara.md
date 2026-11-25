# 5-minute presentation: Barbara's part (Team member 1)

About 2 of the 5 minutes. Order of the whole talk: problem → **architecture** → live demo (Aliénor) →
monitoring (**AI & carbon** + System health) → **carbon trade-offs** → **limits**.
Aliénor: live demo (simulator → alert → doctor-dashboard), carbon-aware scheduling, "System health" dashboard.

## Slide: Architecture (~40 s)

Picture: [diagrams/components/24.11_B_component-diagram_v2.png](../diagrams/components/24.11_B_component-diagram_v2.png)

Say:
- A home device sends one message per minute (SpO₂, airflow, chest and belly) to Kafka `raw-signals`.
- Two paths read the same minute: **alert-check** is never paused (SpO₂ < 80 % → alert in seconds),
  **apnea-detector** finds apnea events and can wait for low carbon.
- **ahi-triage** counts the events of the night, calculates the AHI and severity, writes `results` before 08:00.
- **carbon-scheduler** sends the carbon mode of AT / NO / PL, **model-trainer** trains only in a low-carbon window.
- Everything runs in Kubernetes: the detector scales 1 → 3 pods (3 partitions of `raw-signals`).

## Slide: AI model and its limits (~40 s)

Numbers: [model-limits.md](model-limits.md)

Say:
- Two models, chosen by the carbon mode: **accurate** (F1 0.906) in low carbon, **fast rule** (F1 0.832, about 50×
  less CPU) in high carbon close to 08:00. Far from 08:00 the detector waits instead.
- We label every **minute**, the AHI = event minutes / hours of recording. It is lower than the clinical AHI
  (ucddb025: 94 in the sleep lab, 54 for us): max one event per minute, no sleep time, no EEG arousals.
- So it is a **screening** for the doctor, not a diagnosis. The fast rule rather overestimates: a patient comes
  to the doctor too early, not too late.

## Slide: AI & carbon dashboard (~20 s)

Screenshot of Grafana "AI & carbon" ([monitoring/grafana/dashboards/ai-and-carbon.json](../monitoring/grafana/dashboards/ai-and-carbon.json))
after the demo run.

Say:
- Top row: which model ran, events per hour, severity of the nights.
- Middle: model behaviour (UC6): average confidence, minutes with low confidence, share of event minutes now vs
  last week → alert `ModelConfidenceDrift` / `ApneaEventShareDrift` when the data changes.
- Bottom: gCO₂ per night, per LLM summary, carbon mode, when the detector was paused.

## Slide: Carbon trade-offs (~20 s, shared with Aliénor)

Table: [co2-tradeoffs.md](co2-tradeoffs.md), section 1 and 2.

Say:
- One night in the detector ≈ 0.002 g CO₂; one LLM summary costs more than several nights → first thing to switch off.
- Fast rule saves CPU but costs F1 and makes the AHI too high; waiting costs only time, still before 08:00 (5 / 5).

## Before the demo

- Run the flow once: `bash k8s/e2e.sh` (or `bash scripts/compose-e2e.sh`), see [RUN.md](../RUN.md).
- Take the Grafana screenshot (needs Prometheus + Grafana from Aliénor), or show the `/metrics` counters from `e2e.sh`.
