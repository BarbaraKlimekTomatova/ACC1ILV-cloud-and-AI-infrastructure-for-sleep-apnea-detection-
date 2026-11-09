# ADR 0004: Carbon-aware redeployment

- **Status:** Accepted
- **Date:** 09.11.2026
- **Use cases:** UC5

## Context
Electricity in different regions has different carbon intensity at different times. We want the detector to run where the electricity is cleaner right now. We simulate three regions (AT, NO, PL) as node labels in one cluster, with a carbon signal per region that changes over time (CSV replay).

## Options
1. **Choose a green region once at deployment:** easy, but static. The professor said this is not enough.
2. **Several clusters, one per region:** realistic, but expensive and complex for our project.
3. **Move the pod inside one cluster:** the carbon-scheduler changes the `nodeAffinity` of the detector Deployment, and Kubernetes moves the pod with a rolling update.

## Decision
We use option 3. Every few minutes the carbon-scheduler compares the regions. It moves the detector only if another region is cleaner by more than a threshold (e.g. 20 %) and the last move was more than 15 minutes ago (to avoid moving back and forth).

## Consequences
- The detector follows the cleanest region during the night.
- A move restarts the pod. No data is lost: the new pod continues reading Kafka from the last committed offset (ADR 0001). Alerts are not affected (ADR 0002).
- Moving itself costs a little energy and time, so the threshold and the waiting time must be tuned.
- The regions are simulated with labels, not real data centres.
