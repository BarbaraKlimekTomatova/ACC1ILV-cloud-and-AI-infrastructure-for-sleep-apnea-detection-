# ADR 0024: Google Cloud GKE Standard with self-hosted Kafka and PostgreSQL

- **Date:** 30.10.2026
- **Status:** Accepted
- **Source:** project summary and diagrams from 30.10 (`diagrams/30.10_B_*`)
- **Use cases:** UC5, UC6

## Context
We need a real cloud deployment and want to keep cost low.

## Decision
GKE Standard in a low-CO₂ region (Region Picker). Kafka (Strimzi) and PostgreSQL run inside the cluster. Images in Artifact Registry.

## Alternatives
Managed Kafka and Cloud SQL: less work, but more cost.

## Consequences
Same setup as locally on kind. We run the databases ourselves.
