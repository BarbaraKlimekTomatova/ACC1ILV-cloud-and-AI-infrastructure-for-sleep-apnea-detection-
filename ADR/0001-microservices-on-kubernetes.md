# ADR 0001: Microservices on Kubernetes

- **Date:** 24.10.2026
- **Status:** Superseded by ADR 0008
- **Source:** `diagrams/24.10_A_component-diagram_v1.mmd`
- **Use cases:** UC1–UC7

## Context
The course asks for a cloud system with several microservices on Kubernetes. Each part of the screening (data input, analysis, triage, carbon decisions, dashboard) has a different job.

## Decision
We split the system into 5 microservices: device-simulator, analysis-service, ahi-triage-service, carbon-scheduler-service and dashboard-service. All of them run in one Kubernetes cluster.

## Alternatives
One monolith: easier to build, but it does not show scaling or messaging, which the course wants.

## Consequences
Each service can be built, deployed and scaled alone. We need messaging between them and more deployment files.
