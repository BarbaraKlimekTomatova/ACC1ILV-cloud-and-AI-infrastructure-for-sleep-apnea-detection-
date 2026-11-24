#!/usr/bin/env bash
# K8s base: Strimzi + Kafka + the 5 topics, PostgreSQL with db/init/, node labels region.
# Run from anywhere (Linux, macOS, Git Bash on Windows), with kubectl pointing at the cluster:
#
#   kind create cluster --config k8s/kind/cluster.yaml
#   bash k8s/base/install.sh
#
# Safe to run again (everything is "apply"). Settings:
#   NAMESPACE=default          namespace for everything (the services use the default one)
#   STRIMZI_VERSION=           empty = latest Strimzi from strimzi.io; e.g. 1.0.0 to pin a release
#   WAIT=10m                   how long to wait for Kafka / PostgreSQL / the topics
set -euo pipefail

cd "$(dirname "$0")/../.."                       # repo root
NS="${NAMESPACE:-default}"
WAIT="${WAIT:-10m}"
K="kubectl -n $NS"

step() { printf '\n== %s\n' "$*"; }

# ------------------------------------------------------------------ 1. node labels region
# The carbon-scheduler moves the apnea-detector between these regions (ADR 0004).
# k8s/kind/cluster.yaml sets them already; for any other cluster label the nodes here:
# the worker nodes get AT, NO, PL in turn (a 1-node cluster gets AT only).
step "node labels region = AT / NO / PL"
if [ -z "$(kubectl get nodes -l region -o name)" ]; then
  nodes=$(kubectl get nodes -l '!node-role.kubernetes.io/control-plane' -o name)
  [ -n "$nodes" ] || nodes=$(kubectl get nodes -o name)
  regions=(AT NO PL); i=0
  for n in $nodes; do
    kubectl label --overwrite "$n" "region=${regions[$((i % 3))]}"
    i=$((i + 1))
  done
fi
kubectl get nodes -L region

# ------------------------------------------------------------------ 2. Strimzi operator
step "Strimzi operator (namespace $NS)"
if [ -n "${STRIMZI_VERSION:-}" ]; then
  url="https://github.com/strimzi/strimzi-kafka-operator/releases/download/${STRIMZI_VERSION}/strimzi-cluster-operator-${STRIMZI_VERSION}.yaml"
  # the release file is made for the namespace "myproject"
  curl -fsSL "$url" | sed "s/namespace: .*/namespace: $NS/" | $K apply --server-side --force-conflicts -f -
else
  $K apply --server-side --force-conflicts -f "https://strimzi.io/install/latest?namespace=$NS"
fi
$K rollout status deployment/strimzi-cluster-operator --timeout="$WAIT"

# ------------------------------------------------------------------ 3. PostgreSQL + db/init
step "PostgreSQL (db/init/ as ConfigMap db-init)"
$K create configmap db-init --from-file=db/init/ --dry-run=client -o yaml | $K apply -f -
$K apply -f k8s/base/postgres.yaml

# ------------------------------------------------------------------ 4. Kafka + topics
step "Kafka cluster apnea"
$K apply -f k8s/base/kafka.yaml
$K wait kafka/apnea --for=condition=Ready --timeout="$WAIT"

step "Kafka topics"
$K apply -f k8s/base/kafka-topics.yaml
$K wait kafkatopic --all --for=condition=Ready --timeout="$WAIT"

step "wait for PostgreSQL"
$K rollout status statefulset/postgres --timeout="$WAIT"

step "done"
$K get kafka,kafkatopic,statefulset,svc
cat <<MSG

Base is ready. Addresses for the services (k8s/apnea-config.yaml):
  Kafka       apnea-kafka-bootstrap:9092
  PostgreSQL  postgres:5432  (database sleep_apnea)
Next: kubectl apply -f k8s/   then the nights: kubectl apply -f k8s/jobs/device-simulator.yaml
MSG
