#!/usr/bin/env bash
# Whole flow end to end in docker compose (owner: Barbara): the 5 demo nights go
# device-simulator -> raw-signals -> apnea-detector -> apnea-events -> ahi-triage -> results,
# with alert-check, alert-service and carbon-scheduler running next to them.
# Same checks as k8s/e2e.sh, but on the laptop without Kubernetes.
#
#   bash scripts/compose-e2e.sh             # start (or reuse) compose with the demo override and check
#   FRESH=1 bash scripts/compose-e2e.sh     # first "docker compose down -v": empty database
#
# Fails (exit 1) when a step is missing. Settings:
#   FRESH=0        1 = delete the volumes first (the local database is lost)
#   WAIT_S=600     how long to wait for the 5 results
#   KEEP=1         0 = "docker compose down" at the end
set -euo pipefail

cd "$(dirname "$0")/.."                          # repo root
FRESH="${FRESH:-0}"
WAIT_S="${WAIT_S:-600}"
KEEP="${KEEP:-1}"
NIGHTS="ucddb010 ucddb013 ucddb017 ucddb018 ucddb025"   # the 5 demo nights (P01-P05)
DC="docker compose -f docker-compose.yml -f docker-compose.demo.yml --profile detector --profile triage --profile sim"

step() { printf '\n== %s\n' "$*"; }
fail() { printf '\nFAILED: %s\n' "$*"; $DC ps; exit 1; }
psql() { $DC exec -T postgres psql -U postgres -d sleep_apnea -tAc "$1"; }
in_list() { printf "'%s'," $NIGHTS | sed 's/,$//'; }
offsets() {   # number of messages in a topic (sum over its partitions)
  $DC exec -T kafka /opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server kafka:29092 --topic "$1" \
    | awk -F: '{s += $3} END {print s + 0}'
}
metric() {    # one metric from http://localhost:PORT/metrics (sum over its labels)
  curl -fs "http://localhost:$1/metrics" | awk -v n="$2" '$1 ~ "^"n"({|$)" {s += $2} END {print s + 0}'
}

step "model file models/model.joblib (goes into the detector image)"
if [ ! -f models/model.joblib ]; then
  python services/model-trainer/train.py --no-db --no-carbon
fi
ls -l models/model.joblib

if [ "$FRESH" = "1" ]; then
  step "FRESH=1: docker compose down -v"
  $DC down -v
fi

step "start PostgreSQL, Kafka, topics and all services (without the simulator)"
$DC up --build -d postgres kafka kafka-init carbon-scheduler alert-check alert-service apnea-detector ahi-triage
for port in 8000 8001 8002 8003 8004; do
  for _ in $(seq 60); do curl -fs "http://localhost:$port/metrics" > /dev/null && break; sleep 2; done
  curl -fs "http://localhost:$port/metrics" > /dev/null || fail "nothing on http://localhost:$port/metrics"
done
$DC ps

raw0=$(offsets raw-signals); events0=$(offsets apnea-events); alerts0=$(offsets alerts)
echo "before: raw-signals $raw0, apnea-events $events0, alerts $alerts0"

step "device-simulator (burst, 5 demo nights)"
t0=$(date +%s)
$DC up --build --no-deps device-simulator           # runs in the foreground until all nights are sent
sent=$(( $(offsets raw-signals) - raw0 ))
echo "raw-signals: $sent new messages"
[ "$sent" -gt 0 ] || fail "the simulator sent nothing"

step "apnea-detector analyses every minute (waits up to ${WAIT_S}s)"
end=$(( $(date +%s) + WAIT_S ))
while :; do
  analysed=$(( $(offsets apnea-events) - events0 ))
  echo "apnea-events: $analysed / $sent"
  [ "$analysed" -ge "$sent" ] && break
  [ "$(date +%s)" -lt "$end" ] || fail "only $analysed of $sent minutes analysed"
  sleep 5
done
echo "all minutes analysed after $(( $(date +%s) - t0 )) s"

step "ahi-triage writes one result per night"
while :; do
  n=$(psql "select count(distinct night_id) from results where night_id in ($(in_list))")
  echo "results: $n / 5 demo nights"
  [ "$n" -eq 5 ] && break
  [ "$(date +%s)" -lt "$end" ] || fail "only $n of 5 nights in results"
  sleep 5
done
echo "5 results after $(( $(date +%s) - t0 )) s (a night that was in results before is skipped by ahi-triage)"

step "results"
$DC exec -T postgres psql -U postgres -d sleep_apnea -c \
  "select night_id, ahi, severity, event_count, model, carbon_mode, deadline_met, round(gco2::numeric, 4) as gco2
     from results where night_id in ($(in_list)) order by ahi desc"
bad=$(psql "select count(*) from results where night_id in ($(in_list))
              and (severity is null or ahi is null or model is null)")
[ "$bad" -eq 0 ] || fail "$bad results without AHI, severity or model"
raw=$(psql "select count(*) from raw_nights where night_id in ($(in_list))")
[ "$raw" -eq 5 ] || fail "raw_nights has $raw of 5 nights"

step "alerts and carbon decisions (Aliénor's services)"
alerts_kafka=$(( $(offsets alerts) - alerts0 ))
alerts_db=$(psql "select count(*) from alerts where night_id in ($(in_list))")
decisions=$(psql "select count(*) from carbon_decisions")
echo "alerts topic: $alerts_kafka new   alerts table: $alerts_db   carbon_decisions: $decisions"
if [ "$alerts_kafka" -gt 0 ] && [ "$alerts_db" -eq 0 ]; then
  fail "alert-check sent alerts, but alert-service saved none"
fi

step "Prometheus /metrics"
echo "detector_minutes_total        $(metric 8000 detector_minutes_total)"
echo "detector_gco2_total           $(metric 8000 detector_gco2_total)"
echo "triage_nights_total           $(metric 8001 triage_nights_total)"
echo "triage_deadline_missed_total  $(metric 8001 triage_deadline_missed_total)"
[ "$(metric 8000 detector_minutes_total)" != "0" ] || fail "detector_minutes_total is 0"

if [ "$KEEP" = "0" ]; then
  $DC down
fi
step "OK: 5 demo nights went through device-simulator -> apnea-detector -> ahi-triage -> results in docker compose"
