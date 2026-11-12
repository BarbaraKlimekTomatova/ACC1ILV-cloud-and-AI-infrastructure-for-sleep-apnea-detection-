# ADR 0008: Six microservices, aligned with the proposal

- **Date:** 27.10.2026
- **Status:** Accepted
- **Source:** `diagrams/27.10_B_component flowchart diagram_v2_update.mmd`
- **Use cases:** UC1–UC7

## Context
In v1 the names did not match the proposal, and urgent alerts had no service of their own.

## Decision
We now have 6 microservices: device-simulator, apnea-detector, ahi-triage, alert-service, doctor-dashboard and carbon-scheduler. Supersedes ADR 0001.

## Alternatives
Keep 5 services and put alerts into the dashboard.

## Consequences
Names match the proposal and the use cases. One more service to deploy.
