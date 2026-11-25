#!/usr/bin/env bash
# End-to-end check in Kubernetes (UC1 -> UC2): the device-simulator Job sends the 5 demo nights,
# apnea-detector analyses every minute, ahi-triage writes one row per night into results.
# Owner: Barbara. Needs the base (k8s/base/install.sh) and the services (k8s/apps.sh).
#
#   bash k8s/e2e.sh                 # burst: all nights at once (also shows the HPA)
#   BURST=0 bash k8s/e2e.sh         # nights side by side at SPEED 60 (~7 min)
#
# Fails (exit 1) when a step is missing. Settings:
#   BURST=1        send everything at once (device-simulator BURST)
#   WAIT_S=600     how long to wait for the 5 results
set -euo pipefail

cd "$(dirname "$0")/.."                          # repo root
BURST="${BURST:-1}"
WAIT_S="${WAIT_S:-600}"
NIGHTS="ucddb010 ucddb013 ucddb017 ucddb018 ucddb025"   # the 5 demo nights (P01-P05)

step() { printf '\n== %s\n' "$*"; }
fail() { printf '\nFAILED: %s\n' "$*"; exit 1; }
psql() { kubectl exec postgres-0 -- psql -U postgres -d sleep_apnea -tAc "$1"; }
in_list() { printf "'%s'," $NIGHTS | sed 's/,$//'; }

kafka_pod=$(kubectl get pod -l strimzi.io/cluster=apnea,strimzi.io/kind=Kafka -o name | head -n 1)
[ -n "$kafka_pod" ] || fail "no Kafka pod (run k8s/base/install.sh first)"
offsets() {   # number of messages in a topic (sum over its partitions)
  kubectl exec "$kafka_pod" -- bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic "$1" \
    | awk -F: '{s += $3} END {print s + 0}'
}
metric() {    # sum of one metric over all pods with the label app=$1
  local app=$1 port=$2 name=$3 total=0 v
  for pod in $(kubectl get pod -l "app=$app" --field-selector=status.phase=Running -o name); do
    v=$(kubectl exec "$pod" -- python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:$port/metrics').read().decode())" \
        | awk -v n="$name" '$1 ~ "^"n"({|$)" {s += $2} END {print s + 0}')
    total=$(awk -v a="$total" -v b="$v" 'BEGIN {print a + b}')
  done
  echo "$total"
}

step "services are running"
kubectl rollout status deployment/apnea-detector --timeout=2m
kubectl rollout status deployment/ahi-triage --timeout=2m

raw0=$(offsets raw-signals); events0=$(offsets apnea-events); results0=$(offsets night-results)
echo "before: raw-signals $raw0, apnea-events $events0, night-results $results0"

step "device-simulator Job (BURST=$BURST)"
t0=$(date +%s)
kubectl delete job device-simulator --ignore-not-found --wait=true
sed "/name: BURST/{n;s/value: \"[01]\"/value: \"$BURST\"/;}" k8s/jobs/device-simulator.yaml | kubectl apply -f -
kubectl wait job/device-simulator --for=condition=complete --timeout=15m
kubectl logs job/device-simulator | tail -n 2
sent=$(( $(offsets raw-signals) - raw0 ))
echo "raw-signals: $sent new messages"
[ "$sent" -gt 0 ] || fail "the simulator sent nothing"

step "apnea-detector analyses every minute (waits up to ${WAIT_S}s)"
end=$(( $(date +%s) + WAIT_S ))
max_pods=1
while :; do
  analysed=$(( $(offsets apnea-events) - events0 ))
  replicas=$(kubectl get hpa apnea-detector -o jsonpath='{.status.currentReplicas}' 2>/dev/null || echo 0)
  [ "${replicas:-0}" -gt "$max_pods" ] 2>/dev/null && max_pods=$replicas
  echo "apnea-events: $analysed / $sent   detector pods: $replicas"
  [ "$analysed" -ge "$sent" ] && { t_analysed=$(( $(date +%s) - t0 )); break; }
  [ "$(date +%s)" -lt "$end" ] || fail "only $analysed of $sent minutes analysed"
  sleep 10
done

step "ahi-triage writes one result per night"
n=0
while :; do
  n=$(psql "select count(distinct night_id) from results where night_id in ($(in_list))")
  echo "results: $n / 5 demo nights"
  [ "$n" -eq 5 ] && { t_results=$(( $(date +%s) - t0 )); break; }
  [ "$(date +%s)" -lt "$end" ] || fail "only $n of 5 nights in results"
  sleep 10
done
echo "night-results: $(( $(offsets night-results) - results0 )) new messages (0 when the nights were saved before)"

step "results (table results)"
kubectl exec postgres-0 -- psql -U postgres -d sleep_apnea -c \
  "select night_id, ahi, severity, event_count, model, carbon_mode, deadline_met, round(gco2::numeric, 4) as gco2
     from results where night_id in ($(in_list)) order by ahi desc"
bad=$(psql "select count(*) from results where night_id in ($(in_list))
              and (severity is null or ahi is null or model is null)")
[ "$bad" -eq 0 ] || fail "$bad results without AHI, severity or model"
raw=$(psql "select count(*) from raw_nights where night_id in ($(in_list))")
[ "$raw" -eq 5 ] || fail "raw_nights has $raw of 5 nights"

step "time (NFR deadline 08:00)"
echo "all $sent minutes analysed after ${t_analysed}s, 5 results after ${t_results}s (from the start of the Job)"
late=$(psql "select count(*) from results where night_id in ($(in_list)) and deadline_met is not true")
echo "nights after 08:00: $late"

step "Prometheus /metrics"
echo "detector_minutes_total  $(metric apnea-detector 8000 detector_minutes_total)"
echo "detector_gco2_total     $(metric apnea-detector 8000 detector_gco2_total)"
echo "triage_nights_total     $(metric ahi-triage 8001 triage_nights_total)"
kubectl get hpa apnea-detector
echo "highest number of detector pods in this run: $max_pods"

step "OK: 5 demo nights went through device-simulator -> apnea-detector -> ahi-triage -> results"
