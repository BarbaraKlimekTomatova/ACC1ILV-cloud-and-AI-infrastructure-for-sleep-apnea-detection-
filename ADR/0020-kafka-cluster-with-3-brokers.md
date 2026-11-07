# ADR 0020: Kafka cluster with 3 brokers

- **Date:** 30.10.2026
- **Status:** Accepted
- **Source:** project summary and diagrams from 30.10 (`diagrams/30.10_B_*`)
- **Use cases:** UC1, UC2, UC5

## Context
With 1 broker, one crash stops everything. Nights can wait in Kafka for low-carbon hours, so we must not lose them.

## Decision
3 brokers in KRaft mode, replication factor 3, `min.insync.replicas` 2, 7-day retention. Locally with docker-compose, in the cluster with Strimzi. Supersedes ADR 0016.

## Alternatives
1 broker: simpler, no fault tolerance.

## Consequences
