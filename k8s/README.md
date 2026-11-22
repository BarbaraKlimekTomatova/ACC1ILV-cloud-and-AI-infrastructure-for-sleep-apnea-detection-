# Kubernetes manifests

Plain YAML, one file per service, applied with `kubectl apply -f`. Locally on kind, later on GKE
([doc/gcp-architecture.md](../doc/gcp-architecture.md)).

| File | What | Owner |
|---|---|---|
| `apnea-config.yaml` | ConfigMap `apnea-config` (Kafka address, deadline, demo clock), Secret `apnea-db` (one DB URL per service, ADR 0007), Secret `llm-api` (empty for now) | Barbara |
| `apnea-detector.yaml` | Deployment, Service (`/metrics` 8000), HPA 1–3 pods on CPU 70 %, preferred node region for the carbon-scheduler (ADR 0003, 0004) | Barbara |
| `ahi-triage.yaml` | Deployment with exactly 1 pod (open nights are in memory), Service (`/metrics` 8001) | Barbara |
| `model-trainer.yaml` | CronJob Sunday 02:00 Europe/Vienna, `concurrencyPolicy: Forbid`, PVC `models` for the trained files (ADR 0005) | Barbara |
| Kafka (Strimzi), PostgreSQL, node labels `region` = AT / NO / PL, Prometheus, Grafana, Aliénor's services | K8s base | Aliénor (to do) |

The manifests need the Kafka and PostgreSQL addresses of the base:

- `KAFKA_BOOTSTRAP` in `apnea-config.yaml` (now `kafka:29092`). With Strimzi it is
  `<cluster name>-kafka-bootstrap:9092`, e.g. `apnea-kafka-bootstrap:9092`.
- the host `postgres:5432` in the Secret `apnea-db`.

## Run on kind

```
kind create cluster --name apnea
python services/model-trainer/train.py --no-db
python services/model-trainer/train.py --no-db --model fast
docker build -f services/apnea-detector/Dockerfile -t apnea-detector:dev .
docker build -f services/ahi-triage/Dockerfile -t ahi-triage:dev .
docker build -f services/model-trainer/Dockerfile -t model-trainer:dev .
kind load docker-image apnea-detector:dev ahi-triage:dev model-trainer:dev --name apnea
kubectl apply -f k8s/
kubectl get pods,hpa,cronjob
```

The HPA needs metrics-server (not in kind by default). Start a training by hand:
`kubectl create job --from=cronjob/model-trainer model-trainer-manual`.
Delete the cluster when you do not need it (saves energy): `kind delete cluster --name apnea`.

## Carbon-aware parts (UC5)

- The carbon-scheduler changes `maxReplicas` of the HPA `apnea-detector` (1 in `high_carbon`, 3 in `low_carbon`).
- It changes the `region` in the detector's node affinity to the cleanest region. Kubernetes then moves the pod.
- Alerts never wait: the alert check runs inside the detector with its own consumer group (ADR 0002).
