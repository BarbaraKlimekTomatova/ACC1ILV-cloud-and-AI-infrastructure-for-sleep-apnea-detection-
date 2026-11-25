#!/usr/bin/env bash
# Barbara's part of the kind cluster: images of all services, metrics-server for the HPA,
# then apnea-detector, ahi-triage and model-trainer (k8s/*.yaml). Owner: Barbara.
# Run AFTER the base (Aliénor), from anywhere, with kubectl pointing at the kind cluster:
#
#   kind create cluster --config k8s/kind/cluster.yaml
#   bash k8s/base/install.sh
#   bash k8s/apps.sh
#   bash k8s/e2e.sh
#
# Safe to run again (images are rebuilt and loaded, everything else is "apply"). Settings:
#   CLUSTER=apnea      kind cluster name
#   USE_LLM=           empty = as in apnea-config.yaml; "0" = no LLM summary (CI, no Ollama)
#   SKIP_BUILD=1       do not build / load the images again
#   WAIT=5m            how long to wait for each rollout
set -euo pipefail

cd "$(dirname "$0")/.."                          # repo root
CLUSTER="${CLUSTER:-apnea}"
WAIT="${WAIT:-5m}"
METRICS_SERVER_VERSION="${METRICS_SERVER_VERSION:-v0.7.2}"
IMAGES="apnea-detector ahi-triage model-trainer device-simulator"

step() { printf '\n== %s\n' "$*"; }

# ------------------------------------------------------------------ 1. model file
# The detector image contains models/model.joblib (services/apnea-detector/Dockerfile).
step "model file models/model.joblib"
if [ ! -f models/model.joblib ]; then
  python services/model-trainer/train.py --no-db --no-carbon
fi
ls -l models/model.joblib

# ------------------------------------------------------------------ 2. images -> kind
if [ "${SKIP_BUILD:-0}" != "1" ]; then
  for s in $IMAGES; do
    step "image $s:dev"
    docker build -q -f "services/$s/Dockerfile" -t "$s:dev" .
  done
  step "load the images into the kind cluster $CLUSTER"
  # shellcheck disable=SC2046
  kind load docker-image $(for s in $IMAGES; do printf '%s:dev ' "$s"; done) --name "$CLUSTER"
fi

# ------------------------------------------------------------------ 3. metrics-server (HPA)
# kind has no metrics-server; the kubelets use self-signed certificates, so it needs
# --kubelet-insecure-tls (local cluster only, GKE has its own metrics).
step "metrics-server $METRICS_SERVER_VERSION"
kubectl apply -f "https://github.com/kubernetes-sigs/metrics-server/releases/download/$METRICS_SERVER_VERSION/components.yaml"
if ! kubectl -n kube-system get deployment metrics-server -o jsonpath='{.spec.template.spec.containers[0].args}' \
     | grep -q kubelet-insecure-tls; then
  kubectl -n kube-system patch deployment metrics-server --type=json \
    -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
fi
kubectl -n kube-system rollout status deployment/metrics-server --timeout="$WAIT"

# ------------------------------------------------------------------ 4. Barbara's services
step "apnea-config, apnea-detector, ahi-triage, model-trainer"
kubectl apply -f k8s/
if [ -n "${USE_LLM:-}" ]; then
  kubectl patch configmap apnea-config --type=merge -p "{\"data\":{\"USE_LLM\":\"$USE_LLM\"}}"
fi
# new image or config -> new pods
kubectl rollout restart deployment/apnea-detector deployment/ahi-triage
kubectl rollout status deployment/apnea-detector --timeout="$WAIT"
kubectl rollout status deployment/ahi-triage --timeout="$WAIT"

step "done"
kubectl get pods -o wide -l 'app in (apnea-detector, ahi-triage)'
kubectl get hpa,cronjob
cat <<MSG

Services are running. Next: bash k8s/e2e.sh   (sends the 5 demo nights and checks the results)
MSG
