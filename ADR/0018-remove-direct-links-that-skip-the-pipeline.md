# ADR 0018: Remove direct links that skip the pipeline

- **Date:** 27.10.2026
- **Status:** Accepted
- **Source:** `diagrams/27.10_B_component flowchart diagram_v2_update.mmd`
- **Use cases:** UC1, UC4

## Context
v1 had a REST link from the simulator to the dashboard and the report going straight back to the patient.

## Decision
Patients come to the dashboard only through the pipeline and the database. The doctor's approved result stays in the dashboard; sending it to the patient is out of scope.

## Alternatives
Keep the links: more arrows, more to build.

## Consequences
Cleaner diagram, fewer interfaces.
