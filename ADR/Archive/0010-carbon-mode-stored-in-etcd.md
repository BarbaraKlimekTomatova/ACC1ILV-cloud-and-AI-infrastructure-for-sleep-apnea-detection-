# ADR 0010: Carbon mode stored in etcd

- **Date:** 27.10.2026
- **Status:** Accepted (names changed in ADR 0021)
- **Source:** `diagrams/27.10_B_component flowchart diagram_v2_update.mmd`
- **Use cases:** UC5

## Context
In v1 the detector called the carbon-scheduler by REST. If the scheduler is down, the analysis stops.

## Decision
The carbon-scheduler writes the current mode to etcd. The apnea-detector only reads it. Supersedes ADR 0005.

## Alternatives
Keep REST; or use a Kubernetes ConfigMap (slower to update).

## Consequences
The detector does not depend on the scheduler being up. etcd is a key-value store from the course.
