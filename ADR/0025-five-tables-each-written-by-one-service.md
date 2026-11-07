# ADR 0025: Five tables, each written by one service

- **Date:** 30.10.2026
- **Status:** Accepted (to confirm with the professor)
- **Source:** project summary and diagrams from 30.10 (`diagrams/30.10_B_*`)
- **Use cases:** UC1–UC4

## Context
ADR 0003 said “tables per service”. We now know exactly which tables we need.

## Decision
Tables: `patients` (A), `raw_nights` (B), `results` (A), `alerts` (B), `decisions` = audit log (A). Patients have a label, no real name.

## Alternatives
More tables (devices, reports).

## Consequences
Small, clear data model; pseudonymised.
