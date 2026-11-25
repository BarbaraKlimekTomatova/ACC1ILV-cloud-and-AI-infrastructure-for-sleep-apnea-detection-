# Kubernetes manifests

Plain YAML, one file per service, applied with `kubectl apply -f`. Locally on kind, later on GKE
([doc/gcp-architecture.md](../doc/gcp-architecture.md)).

| File | What | Owner |
|---|---|---|
| `apnea-config.yaml` | ConfigMap `apnea-config` (Kafka address, deadline, demo clock), Secret `apnea-db` (one DB URL per service, ADR 0007), Secret `llm-api` (empty for now) | Barbara |
| `apnea-detector.yaml` | Deployment, Service (`/metrics` 8000), HPA 1–3 pods on CPU 70 %, preferred node region for the carbon-scheduler (ADR 0003, 0004) | Barbara |
| `ahi-triage.yaml` | Deployment with exactly 1 pod (open nights are in memory), Service (`/metrics` 8001) | Barbara |
| `model-trainer.yaml` | CronJob Sunday 02:00 Europe/Vienna, `concurrencyPolicy: Forbid`, PVC `models` for the trained files (ADR 0005) | Barbara |
| `apps.sh` | Barbara's part on kind, after the base: trains `models/model.joblib` if missing, builds and loads the images of all services, installs metrics-server (for the HPA), applies `k8s/*.yaml`, waits for the rollouts | Barbara |
| `e2e.sh` | end-to-end check: device-simulator Job (burst) → apnea-detector → ahi-triage → table `results`; checks the Kafka offsets, `raw_nights`, `results` and `/metrics`, fails when a step is missing. The workflow `k8s-e2e` runs base + `apps.sh` + `e2e.sh` on kind | Barbara |
| `kind/cluster.yaml` | kind cluster `apnea`: 1 control plane + 3 workers with the label `region` = AT / NO / PL (ADR 0004) | Aliénor |
| `base/install.sh` | installs the K8s base in this order: region labels (if missing), Strimzi operator, ConfigMap `db-init` from `db/init/`, PostgreSQL, Kafka, topics; waits until each is ready | Aliénor |
| `base/kafka.yaml` | Strimzi Kafka cluster `apnea` (KRaft, 1 node = broker + controller, API `kafka.strimzi.io/v1`), Topic Operator | Aliénor |
| `base/kafka-topics.yaml` | the 5 KafkaTopic resources: `raw-signals` (3 partitions), `alerts`, `apnea-events`, `night-results`, `carbon-signal` | Aliénor |
| `base/postgres.yaml` | PostgreSQL 16 StatefulSet + Service `postgres:5432`, `db/init/*.sql` mounted from the ConfigMap `db-init` | Aliénor |
| `jobs/device-simulator.yaml` | Job: sends the 5 demo nights once (UC1). In its own folder so `kubectl apply -f k8s/` does not start it | Aliénor |
| Prometheus, Grafana, Aliénor's other services | | Aliénor (to do) |

Addresses of the base (used in `apnea-config.yaml`):

- Kafka: `apnea-kafka-bootstrap:9092` (`KAFKA_BOOTSTRAP`). Strimzi names the Service
  `<cluster name>-kafka-bootstrap`. docker compose still uses `kafka:29092`.
- PostgreSQL: `postgres:5432`, database `sleep_apnea` (Secret `apnea-db`).

`tests/k8s` checks that these addresses, the topics and the labels fit together
(`pytest tests/k8s`, no cluster needed). The workflow `k8s-base` also runs everything on kind.

## Run on kind

Three scripts, in this order (bash; on Windows Git Bash):

```
kind create cluster --config k8s/kind/cluster.yaml     # cluster "apnea" with the 3 region nodes
bash k8s/base/install.sh                               # Strimzi, Kafka + topics, PostgreSQL (~3-5 min)
bash k8s/apps.sh                                       # images, metrics-server, apnea-detector, ahi-triage, model-trainer
bash k8s/e2e.sh                                        # 5 demo nights -> results, fails if a step is missing
```

`USE_LLM=0 bash k8s/apps.sh` turns the LLM summary off (no Ollama on the laptop). `BURST=0 bash k8s/e2e.sh`
sends the nights side by side instead of all at once (~7 min). The same steps by hand:

```
kind create cluster --config k8s/kind/cluster.yaml     # cluster "apnea" with the 3 region nodes
bash k8s/base/install.sh                               # Strimzi, Kafka + topics, PostgreSQL (~3-5 min)
python services/model-trainer/train.py --no-db
docker build -f services/apnea-detector/Dockerfile -t apnea-detector:dev .
docker build -f services/ahi-triage/Dockerfile -t ahi-triage:dev .
docker build -f services/model-trainer/Dockerfile -t model-trainer:dev .
docker build -f services/device-simulator/Dockerfile -t device-simulator:dev .
kind load docker-image apnea-detector:dev ahi-triage:dev model-trainer:dev device-simulator:dev --name apnea
kubectl apply -f k8s/
kubectl get pods,hpa,cronjob
kubectl apply -f k8s/jobs/device-simulator.yaml       # send the 5 demo nights
kubectl logs -f job/device-simulator
```

On Windows run `install.sh` in Git Bash. Without bash, the same steps by hand:

```
kubectl label node apnea-worker region=AT; kubectl label node apnea-worker2 region=NO; kubectl label node apnea-worker3 region=PL   # only if not made from kind/cluster.yaml
kubectl apply --server-side -f "https://strimzi.io/install/latest?namespace=default"
kubectl create configmap db-init --from-file=db/init/ --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f k8s/base/postgres.yaml -f k8s/base/kafka.yaml
kubectl wait kafka/apnea --for=condition=Ready --timeout=10m
kubectl apply -f k8s/base/kafka-topics.yaml
kubectl get kafkatopic                                 # all 5 READY True
```

Pin the Strimzi version with `STRIMZI_VERSION=1.0.0 bash k8s/base/install.sh` (default: latest;
the manifests use the v1 API, Strimzi 0.49 or newer). Check the database:
`kubectl exec -it postgres-0 -- psql -U postgres -d sleep_apnea -c "select * from patients"`.

The HPA needs metrics-server (not in kind by default, `k8s/apps.sh` installs it). Start a training by hand:
`kubectl create job --from=cronjob/model-trainer model-trainer-manual`.
Delete the cluster when you do not need it (saves energy): `kind delete cluster --name apnea`.

## Carbon-aware parts (UC5)

- The carbon-scheduler changes `maxReplicas` of the HPA `apnea-detector` (1 in `high_carbon`, 3 in `low_carbon`).
- It changes the `region` in the detector's node affinity to the cleanest region. Kubernetes then moves the pod.
- Alerts never wait: the alert check runs inside the detector with its own consumer group (ADR 0002).
