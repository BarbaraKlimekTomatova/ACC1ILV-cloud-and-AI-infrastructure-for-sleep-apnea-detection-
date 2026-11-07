# ADR 0015: kind cluster for local development

- **Date:** 27.10.2026
- **Status:** Accepted (cloud in ADR 0024)
- **Source:** `diagrams/27.10_B_component flowchart diagram_v2_update.mmd`
- **Use cases:** UC1–UC7

## Context
We need Kubernetes on our laptops for free.

## Decision
We use kind locally. The nodes get region labels AT / NO / PL.

## Alternatives
minikube: also fine, kind is lighter for multi-node clusters.

## Consequences
Free and quick. Same YAML can later go to the cloud.
