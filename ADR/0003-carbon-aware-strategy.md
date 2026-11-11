# ADR 0003: Carbon-aware strategy

- **Status:** Accepted
- **Date:** 09.11.2026
- **Use cases:** UC2, UC5

## Context
The system must change its behaviour when the (simulated) carbon intensity changes, and we must measure the effect. Only "check the signal and try later" or "choose a green region once" is not enough. The SLOs must still hold: every night analysed before 08:00, alerts within 5 seconds.

## Options
1. **Only time-shifting:** wait for low carbon. Risky: if the night stays "dirty", the 08:00 deadline is missed.
2. **Only model switching:** always run now, but with the fast model when carbon is high. Saves energy, but loses accuracy even when there was time to wait.
3. **Combination:** time-shifting, model switching and a lower scaling limit, decided by carbon mode and the time left until 08:00.

## Decision
We use option 3. The carbon-scheduler reads the carbon intensity and publishes the mode (`low_carbon` / `high_carbon`) to a small Kafka topic `carbon-signal` (we do not need a separate etcd for one value). The services react:

| Situation | Behaviour |
| --- | --- |
| `low_carbon` | run now with the accurate model, HPA up to 3 pods |
| `high_carbon`, deadline far | pause the analysis (nights wait in Kafka), HPA max 1 pod |
| `high_carbon`, deadline close | run now with the fast model |

CodeCarbon measures the CO₂ of every analysis, so we can compare the modes.

## Consequences
- The system really changes its configuration (model, number of pods, timing), and we can show the CO₂ difference.
- The deadline is always kept, because close to 08:00 the fast model runs anyway.
- CodeCarbon only measures the energy inside our containers, not the network, storage or the rest of the node.
