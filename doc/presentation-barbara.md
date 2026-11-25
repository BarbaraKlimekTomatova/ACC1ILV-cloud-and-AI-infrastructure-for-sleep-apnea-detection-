# Live demo: Barbara's part (Team member 1)

About 2 of the 5 minutes, shown live in the terminal on the kind cluster `apnea`.
What I show: the services in Kubernetes, one demo run through the detector (HPA 1 → 3 pods), the results
in PostgreSQL, the metrics, the carbon mode switch and the limits of the model.
Aliénor shows: simulator → alert → doctor-dashboard, carbon-scheduler, "System health" dashboard.

## 0. Before the presentation (not live)

Cluster up and everything deployed, see [RUN.md](../RUN.md) section 2:
```
kind create cluster --config k8s/kind/cluster.yaml
bash k8s/base/install.sh
USE_LLM=0 bash k8s/apps.sh
```
Open 2 terminals in the repo folder, `source .venv312/bin/activate` in both.
Terminal 2 shows the HPA the whole time:
```
kubectl get hpa apnea-detector -w
```
Run the demo once before, so the images are loaded and the results table is not empty.

## 1. The system in Kubernetes (~20 s)

```
kubectl get nodes -L region
kubectl get pods -o wide
```
Say: 3 worker nodes labelled AT / NO / PL (simulated regions). Kafka (Strimzi), PostgreSQL, my
apnea-detector and ahi-triage, model-trainer as a CronJob. The detector has an HPA 1 → 3 pods,
max 3 because `raw-signals` has 3 partitions (ADR 0001).

## 2. One demo run: 5 nights through the detector (~50 s)

```
bash k8s/e2e.sh
```
Say while it runs:
- the device-simulator Job sends the 5 demo nights at once (2018 minutes) to `raw-signals`,
- apnea-detector analyses every minute with the accurate model (low carbon) → `apnea-events`,
- terminal 2: the HPA goes from 1 to 3 pods,
- ahi-triage counts the events of each night → AHI and severity → table `results`.

At the end the script prints the results table and `OK`. Point at it:
ucddb025 severe 53.9, ucddb010 moderate 21.5, ucddb018 normal 0.7, all `deadline_met = t`, gCO₂ per night.

## 3. Metrics of the detector (~20 s)

```
kubectl port-forward deployment/apnea-detector 8000:8000 &
curl -s localhost:8000/metrics | grep -E '^detector_(minutes_total|gco2_total|confidence_(sum|count))'
```
Say: Prometheus counters per model and event, the confidence of the model (for drift, UC6) and the gCO₂
estimate of the analysis. If Aliénor's Grafana runs: open the "AI & carbon" dashboard instead.

## 4. Carbon mode: fast model close to 08:00 (~30 s)

```
kubectl patch configmap apnea-config --type=merge -p '{"data":{"DEFAULT_CARBON_MODE":"high_carbon","DEMO_TIME":"06:30"}}'
kubectl rollout restart deployment/apnea-detector deployment/ahi-triage
kubectl rollout status deployment/apnea-detector
kubectl exec postgres-0 -- psql -U postgres -d sleep_apnea -c "delete from decisions where result_id in (select result_id from results where night_id like 'ucddb0%'); delete from results where night_id like 'ucddb0%'"
bash k8s/e2e.sh
```
Say: high carbon and 08:00 is close (06:30) → the detector uses the fast rule instead of waiting
(ADR 0003). In the table `model = fast`, `carbon_mode = high_carbon`. At 23:00 it would pause instead.
The `delete` removes the old results of the demo nights and the doctor's decisions on them
(ahi-triage skips a night that is already in `results`), so the table shows the new fast-model rows.
Do step 4 after Aliénor's doctor-dashboard part, or her decisions from the demo are gone.

Back to normal afterwards:
```
kubectl patch configmap apnea-config --type=merge -p '{"data":{"DEFAULT_CARBON_MODE":"low_carbon","DEMO_TIME":""}}'
kubectl rollout restart deployment/apnea-detector deployment/ahi-triage
```

## 5. Limits of the model (~20 s)

```
python scripts/ahi_vs_clinical.py
```
Say (numbers in [model-limits.md](model-limits.md)):
- our AHI is lower than the clinical one (ucddb025: 94 in the sleep lab, 54 for us): one event per minute
  at most, hours of recording instead of sleep, no EEG,
- the fast rule overestimates (ucddb013 moderate → severe): safe for triage, the patient comes too early,
- so it is a screening for the doctor, not a diagnosis.

## 6. CO₂ in one sentence (~10 s)

From [co2-tradeoffs.md](co2-tradeoffs.md): training 0.021 g, one night 0.002–0.003 g, one LLM summary
more than several nights, so in high carbon the LLM goes off first.

## If something fails live

| Problem | Do |
| --- | --- |
| `e2e.sh` hangs at "apnea-events" | `kubectl logs deployment/apnea-detector --tail=30` |
| pods `ImagePullBackOff` | `SKIP_BUILD=0 bash k8s/apps.sh` (images not loaded into kind) |
| port 8000 busy | `kill %1` and run the port-forward again |
| no cluster | backup: `bash scripts/compose-e2e.sh` (same flow in docker compose) |
