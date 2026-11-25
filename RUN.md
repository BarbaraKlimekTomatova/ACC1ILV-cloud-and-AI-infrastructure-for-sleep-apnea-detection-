# How to run the project

Two ways: **docker compose** (quick, no Kubernetes) or **Kubernetes on kind** (the way we deploy, with
HPA and the region nodes). All commands run from the repo root.

## 1. Requirements (once)

| Tool | Why | Check |
| --- | --- | --- |
| Docker Desktop (running) | images, docker compose, kind | `docker version` shows a Server part |
| Python **3.12** (3.12–3.14, not 3.15: no confluent-kafka wheel yet) | train the model, tests | `python3.12 --version` |
| kind + kubectl | local Kubernetes cluster | `kind version`, `kubectl version --client` |
| bash | the k8s scripts (on Windows: Git Bash) | |
| Ollama (optional) | LLM summary for the doctor, `ollama pull llama3.2:1b` | without it: `USE_LLM=0` |

macOS: `brew install kind kubectl`.

```
python3.12 -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt
python services/model-trainer/train.py --no-db     # -> models/model.joblib (not in git, ~1 min)
```

In VS Code pick the interpreter `.venv312/bin/python` (Cmd+Shift+P → "Python: Select Interpreter").

## 2. Kubernetes on kind (deployment)

```
kind create cluster --config k8s/kind/cluster.yaml   # cluster "apnea": control plane + 3 nodes AT / NO / PL
bash k8s/base/install.sh                             # Strimzi Kafka + 5 topics, PostgreSQL with db/init/ (~3-5 min)
USE_LLM=0 bash k8s/apps.sh                           # images, metrics-server, apnea-detector, ahi-triage, model-trainer
bash k8s/e2e.sh                                      # 5 demo nights -> results (~2 min), fails if a step is missing
```

The end of `e2e.sh` shows the table `results` (AHI and severity of the 5 nights), the `/metrics` counters
and the HPA (1 → 3 detector pods during the burst), then `OK: 5 demo nights went through ...`.

| Script | Owner | What it does |
| --- | --- | --- |
| `k8s/kind/cluster.yaml` | Aliénor | kind cluster with the region labels (ADR 0004) |
| `k8s/base/install.sh` | Aliénor | region labels, Strimzi, Kafka, topics, PostgreSQL |
| `k8s/apps.sh` | Barbara | builds and loads all images, metrics-server, Barbara's services |
| `k8s/e2e.sh` | Barbara | device-simulator Job → apnea-detector → ahi-triage → `results`, checks every step |

Options: `USE_LLM=1 bash k8s/apps.sh` uses Ollama on the laptop (`host.docker.internal:11434`).
`BURST=0 bash k8s/e2e.sh` sends the nights side by side like a real night (~7 min).
After a code change: `bash k8s/apps.sh` again (rebuilds the images and restarts the pods).

### Look inside

```
kubectl get pods -o wide                              # which node (region) each pod runs on
kubectl get hpa apnea-detector -w                     # detector pods during a burst
kubectl logs deployment/apnea-detector -f
kubectl logs deployment/ahi-triage -f
kubectl exec -it postgres-0 -- psql -U postgres -d sleep_apnea -c "select night_id, ahi, severity, model from results"
kubectl port-forward svc/apnea-detector 8000:8000     # then http://localhost:8000/metrics
kubectl create job --from=cronjob/model-trainer model-trainer-manual   # start a training by hand
```

Send the nights again: `bash k8s/e2e.sh` (nights already in `results` are not saved twice).

### Stop

```
kind delete cluster --name apnea                      # deletes everything, saves energy
```

## 3. docker compose (without Kubernetes)

```
docker compose --profile detector --profile triage --profile sim up --build
```

PostgreSQL `localhost:5432`, Kafka `localhost:9092`, `/metrics` on ports 8000–8004.
Without Ollama set `USE_LLM: "0"` for ahi-triage in `docker-compose.yml`.
Stop with `docker compose down`, start from zero (empty database) with `docker compose down -v`.

## 4. Tests (no Docker needed)

```
pytest tests/common tests/apnea-detector tests/ahi-triage tests/model-trainer tests/monitoring tests/k8s
```

The same tests run in GitHub Actions (`.github/workflows/`), `k8s-base` and `k8s-e2e` also start a kind cluster.

## Problems

| Problem | Fix |
| --- | --- |
| `pip install` fails on `confluent-kafka` | Python 3.15 is too new, use the `.venv312` (Python 3.12) |
| red imports in VS Code | wrong interpreter, pick `.venv312/bin/python`; open the repo folder itself, not its parent |
| `apps.sh`: `models/model.joblib` missing | `python services/model-trainer/train.py --no-db` (apps.sh also does it) |
| pods `ErrImagePull` | the image is not in kind: `bash k8s/apps.sh` (or `kind load docker-image <name>:dev --name apnea`) |
| HPA shows `<unknown>` | metrics-server is still starting, wait a minute (`apps.sh` installs it) |
| detector / triage restart at the start | Kafka or PostgreSQL not ready yet: run `k8s/base/install.sh` first, they recover by themselves |
