# ADR 0001: Kafka as a buffer for time-shifting

- **Status:** Accepted
- **Date:** 09.11.2026
- **Use cases:** UC1, UC2, UC5

## Context
The night analysis is not urgent. It only has to be ready by 08:00, so we want it to wait for electricity with low CO₂. Nights must not be lost while they wait, even if a service or a broker stops. Nights also arrive in bursts (many patients send data in the morning).

## Options
1. **Direct calls between services:** simple, but nothing can wait. If the detector is paused or down, the data is lost or the sender is blocked.
2. **A "pending" table in PostgreSQL:** services poll the table. Works for waiting, but polling wastes energy, and many readers on one table are hard to scale.
3. **Kafka:** messages are stored for 7 days, consumers can pause and continue later from the same place, and several consumer groups can read the same data independently.

## Decision
We use Kafka with three topics (`raw-signals`, `apnea-events`, `night-results`). The detector pauses reading while the carbon intensity is high, and the nights wait in Kafka. We run 3 brokers with replication factor 3, so one broker can fail without data loss.

## Consequences
- Time-shifting is possible without extra code: pausing = not reading.
- The burst is buffered, and `raw-signals` has 3 partitions, so up to 3 detector pods can share the work.
- **Sustainability trade-off:** 3 brokers use about three times the memory and energy of one broker. We accept this, because losing a night means the patient has to repeat the measurement at home. Locally we can run 1 broker to save resources.
- We have to run and monitor Kafka ourselves (Strimzi on Kubernetes).
