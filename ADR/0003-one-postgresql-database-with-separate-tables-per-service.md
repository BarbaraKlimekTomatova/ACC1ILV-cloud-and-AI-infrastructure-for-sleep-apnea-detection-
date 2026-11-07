# ADR 0003: One PostgreSQL database with separate tables per service

- **Date:** 24.10.2026
- **Status:** Accepted (made more exact in ADR 0025)
- **Source:** `diagrams/24.10_A_component-diagram_v1.mmd`
- **Use cases:** UC1–UC4

## Context
We need to store patients, results and the doctor's decisions. One database per service is the textbook way, but it is a lot of work for a 2-person project.

## Decision
We use one PostgreSQL database. Each service has its own tables.

## Alternatives
One database per service: cleaner, but more pods, more config and more work.

## Consequences
Easy to run and to back up. We must keep the rule that a service only writes its own tables.
