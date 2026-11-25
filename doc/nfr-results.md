# Non-functional requirements: measured results

The four requirements from the [README](../README.md#use-cases) and what we measured.
Run: kind cluster `apnea` on a MacBook (Docker Desktop), 24 Nov 2026, `bash k8s/e2e.sh` with the
5 demo nights in burst mode (all 2018 minutes at once), accurate model, low_carbon, no LLM.
Repeat it with [RUN.md](../RUN.md), section 2.

| Requirement | Target | Result | Status | Who |
| --- | --- | --- | --- | --- |
| Scalability | detector scales 1 → 3 pods under load and back | 1 → 3 pods during the burst (HPA at 45 % / 70 % CPU right after), 2018 / 2018 minutes analysed | ✅ | Barbara |
| Deadline | every night analysed before 08:00 | 5 / 5 nights `deadline_met = true` | ✅ (see note) | Barbara |
| Alert latency | alert at the doctor within 5 s | `alert_service_latency_seconds`, needs alert-check and alert-service in the cluster | 🟡 | Aliénor |
| No data loss | a night survives a stopped service or one stopped Kafka broker | needs 3 Kafka brokers (the base has 1 now) | 🟡 | Aliénor |

## Scalability (HPA)

`k8s/apnea-detector.yaml`: HPA min 1, max 3 pods at 70 % CPU. Max 3 because `raw-signals` has 3 partitions,
a 4th pod would have nothing to read (ADR 0001).

```
apnea-events: 1979 / 2018   detector pods: 1
apnea-events: 2018 / 2018   detector pods: 3
NAME             REFERENCE                   TARGETS        MINPODS   MAXPODS   REPLICAS
apnea-detector   Deployment/apnea-detector   cpu: 45%/70%   1         3         3
```

The burst is short (2018 minutes take about a minute on one pod), so the 2nd and 3rd pod came when most of
the work was done. To show the scaling longer in the demo: `COPIES=4` in `k8s/jobs/device-simulator.yaml`
(20 nights). The HPA scales back to 1 pod about 5 minutes after the load is gone (Kubernetes default).

## Deadline 08:00

ahi-triage sets `deadline_met = finished <= the first 08:00 (Vienna) after the night started`.

| Night | AHI | Severity | Model | Deadline met | gCO₂ |
| --- | ---: | --- | --- | --- | ---: |
| ucddb025 | 53.9 | severe | accurate | yes | 0.0018 |
| ucddb010 | 21.5 | moderate | accurate | yes | 0.0022 |
| ucddb013 | 12.0 | mild | accurate | yes | 0.0015 |
| ucddb017 | 11.7 | mild | accurate | yes | 0.0015 |
| ucddb018 | 0.7 | normal | accurate | yes | 0.0020 |

Note: the run was in the evening, so 08:00 was far away. The harder case is the demo clock close to
08:00, where the detector must switch to the fast model in high carbon (ADR 0003):
`DEMO_TIME: "06:30"` and `DEFAULT_CARBON_MODE: "high_carbon"` in `k8s/apnea-config.yaml`, then
`bash k8s/apps.sh` and `bash k8s/e2e.sh`. `e2e.sh` prints the time from the start of the Job until all
minutes are analysed and until the 5 results are saved, and the number of nights after 08:00.

## CO₂ of this run

`detector_gco2_total` = 0.009 g for the 5 nights, about 0.002 g per night (CPU time × CPU power × carbon
intensity, estimate). See [model-limits.md](model-limits.md) for what the fast model would change.
