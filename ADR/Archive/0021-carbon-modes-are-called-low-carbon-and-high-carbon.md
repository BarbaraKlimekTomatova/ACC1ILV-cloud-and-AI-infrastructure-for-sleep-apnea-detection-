# ADR 0021: Carbon modes are called low_carbon and high_carbon

- **Date:** 30.10.2026
- **Status:** Accepted
- **Source:** project summary and diagrams from 30.10 (`diagrams/30.10_B_*`)
- **Use cases:** UC5

## Context
“green / dirty” is not clear and sounds unprofessional.

## Decision
The etcd key `/sleep-apnea/carbon_mode` has the value `low_carbon` or `high_carbon` (plus the intensity in gCO₂/kWh). Same names everywhere.

## Alternatives
green / dirty.

## Consequences
Clear names, used in component diagram v3 and sequence diagram v2.
