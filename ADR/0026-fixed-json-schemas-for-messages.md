# ADR 0026: Fixed JSON schemas for messages

- **Date:** 30.10.2026
- **Status:** Accepted
- **Source:** project summary and diagrams from 30.10 (`diagrams/30.10_B_*`)
- **Use cases:** UC1, UC2, UC3

## Context
Two people build services that talk to each other.

## Decision
JSON schemas in `schemas/` for `raw-signals`, `apnea-events`, `night-results` and the ZeroMQ `alert`. Message key = `patient_id`.

## Alternatives
Avro with a schema registry: stronger, but more setup.

## Consequences
We can work in parallel and test messages against the schema.
