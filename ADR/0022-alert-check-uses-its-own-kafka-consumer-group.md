# ADR 0022: Alert check uses its own Kafka consumer group

- **Date:** 30.10.2026
- **Status:** Accepted
- **Source:** project summary and diagrams from 30.10 (`diagrams/30.10_B_*`)
- **Use cases:** UC3, UC5

## Context
In high_carbon mode the detector pauses reading `raw-signals`. Then alerts would also wait.

## Decision
The alert check reads `raw-signals` with its own consumer group `apnea-alerts` that is never paused. The analysis uses the group `apnea-detector`, which can be paused.

## Alternatives
Separate topic for alerts.

## Consequences
Alerts always come at once, even when analysis waits.
