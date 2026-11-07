# ADR 0005: Analysis service asks the carbon-scheduler by REST

- **Date:** 24.10.2026
- **Status:** Superseded by ADR 0010
- **Source:** `diagrams/24.10_A_component-diagram_v1.mmd`
- **Use cases:** UC5

## Context
The analysis must know which model to use and if it should run now or later, based on carbon intensity.

## Decision
The analysis-service calls the carbon-scheduler-service over REST before each analysis. The carbon-scheduler reads carbon intensity from a CSV file or an API.

## Alternatives
Each service reads the carbon data itself: duplicated logic.

## Consequences
Simple to understand. The analysis depends on the carbon-scheduler being up.
