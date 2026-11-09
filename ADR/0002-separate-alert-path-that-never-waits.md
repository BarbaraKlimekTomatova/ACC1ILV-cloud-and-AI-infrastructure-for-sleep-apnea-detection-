# ADR 0002: Separate alert path that never waits

- **Status:** Accepted
- **Date:** 09.11.2026
- **Use cases:** UC3, UC5

## Context
When SpO₂ goes below 80 %, the doctor must get an alert within 5 seconds. But the normal analysis is paused when the carbon intensity is high (ADR 0001). The alert must not wait together with the analysis.

## Options
1. **Alert check inside the paused analysis:** simplest, but the alert would wait for hours. Not acceptable.
2. **Separate channel with ZeroMQ:** fast, but it adds another technology just for one message type, and messages are lost if the alert-service is down.
3. **Separate Kafka consumer group and an `alerts` topic:** the alert check reads `raw-signals` with its own consumer group that is never paused, and writes to an `alerts` topic that the alert-service reads.

## Decision
We use option 3. The alert check is a small, cheap rule (SpO₂ < 80 %), so running it all the time costs very little energy. We remove ZeroMQ.

## Consequences
- Alerts are independent of the carbon mode, and they are not lost if the alert-service restarts.
- One technology less (no ZeroMQ).
- Only the cheap rule runs during high carbon; the expensive AI model still waits.
