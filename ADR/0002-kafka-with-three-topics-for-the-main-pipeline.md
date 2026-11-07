# ADR 0002: Kafka with three topics for the main pipeline

- **Date:** 24.10.2026
- **Status:** Accepted (extended by ADR 0016 and 0020)
- **Source:** `diagrams/24.10_A_component-diagram_v1.mmd`
- **Use cases:** UC1, UC2

## Context
Data goes in one direction: raw signals → detected events → night results. Services should not wait for each other.

## Decision
We use Kafka with 3 topics: `raw-signals`, `apnea-events`, `night-results`. Each service reads one topic and writes the next one.

## Alternatives
REST calls between services: simple, but a slow or stopped service blocks the others and data can be lost.

## Consequences
Services are loosely coupled and messages are kept if a service is down. We have to run and monitor Kafka.
