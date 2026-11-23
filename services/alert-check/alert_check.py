"""alert-check (UC3, ADR 0002). Owner: Aliénor.

    python services/alert-check/alert_check.py

Reads raw-signals with its OWN consumer group (`alert-check`), which is never paused,
so alerts never wait for low carbon. If the lowest valid SpO2 of a minute is below 80 %,
it sends one message to the `alerts` topic (kafka/schemas/alerts-value.schema.json),
key = patient_id. The alert-service reads it and stores it in the `alerts` table.

No model, no database: one comparison per minute, so running it all night costs almost nothing.

The file has two halves:
  1. the logic (no Kafka), so the tests run without it
  2. Kafka, Prometheus metrics and the start

Offsets are stored only after the alert was delivered to Kafka (at least once): an alert can
arrive twice, never zero times. The alert-service skips a second copy of the same minute.
Settings: environment variables, see README.md.
"""

import json
import logging
import math
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- settings
env = os.environ.get
KAFKA = env("KAFKA_BOOTSTRAP", "localhost:9092")                     # kafka:29092 inside Docker
GROUP = env("GROUP_ID", "alert-check")
IN_TOPIC, OUT_TOPIC = env("IN_TOPIC", "raw-signals"), env("OUT_TOPIC", "alerts")
SCHEMA_DIR = Path(env("SCHEMA_DIR", str(ROOT / "kafka" / "schemas")))
ALERT_THRESHOLD = float(env("ALERT_THRESHOLD", "80"))                 # %, alert when SpO2 < this
MIN_VALID_SPO2 = float(env("MIN_VALID_SPO2", "50"))                  # lower = sensor artefact
METRICS_PORT = int(env("METRICS_PORT", "8002"))

log = logging.getLogger("alert-check")
RAW_SCHEMA = Draft202012Validator(json.loads((SCHEMA_DIR / "raw-signals-value.schema.json").read_text()))
ALERT_SCHEMA = Draft202012Validator(json.loads((SCHEMA_DIR / "alerts-value.schema.json").read_text()))


# ================================================================ 1. LOGIC (no Kafka)

def spo2_min(values, low_limit=MIN_VALID_SPO2):
    """Lowest real SpO2 of the minute. null/NaN = drop-out, < 50 % or > 100 % = artefact.
    None if the minute has no valid value at all."""
    ok = [float(v) for v in values
          if v is not None and not math.isnan(v) and low_limit <= v <= 100]
    return min(ok) if ok else None


def alert_for(raw, threshold=ALERT_THRESHOLD, now=None):
    """raw-signals message -> alerts message, or None if SpO2 stayed >= threshold."""
    low = spo2_min(raw["spo2"])
    if low is None or low >= threshold:
        return None
    now = now or datetime.now(timezone.utc)
    alert = {"patient_id": raw["patient_id"], "night_id": raw["night_id"],
             "minute": int(raw["minute"]), "spo2_min": round(low, 1),
             "threshold": threshold, "detected_at": now.isoformat()}
    if alert["spo2_min"] >= threshold:       # rounding (79.96 -> 80.0) must not break the schema
        alert["spo2_min"] = math.floor(low * 10) / 10
    ALERT_SCHEMA.validate(alert)
    return alert


def parse_raw(value):
    """Kafka value -> valid raw-signals dict, or None (a bad message is logged and skipped)."""
    try:
        raw = json.loads(value)
        RAW_SCHEMA.validate(raw)
        return raw
    except Exception as e:  # noqa: BLE001  one bad message must not stop the alerts
        log.error("bad raw-signals message: %s", str(e)[:200])
        return None


def encode(message):
    return json.dumps(message, separators=(",", ":")).encode()


# ================================================================ 2. KAFKA, METRICS, START

def run(consumer, producer, stop, metrics=None):
    """Main loop. `consumer` / `producer` are confluent_kafka objects (or fakes in the tests)."""
    consumer.subscribe([IN_TOPIC])
    while not stop():
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        raw = parse_raw(msg.value())
        if raw:
            if metrics:
                metrics["minutes"].inc()
            alert = alert_for(raw)
            if alert:
                producer.produce(OUT_TOPIC, key=raw["patient_id"], value=encode(alert))
                if producer.flush(5) > 0:                      # not delivered: do not store the offset
                    raise RuntimeError("alert could not be delivered to Kafka")
                if metrics:
                    metrics["alerts"].inc()
                log.info("ALERT %s minute %s SpO2 %.1f %%", raw["night_id"], raw["minute"], alert["spo2_min"])
        consumer.store_offsets(msg)
    producer.flush(10)
    consumer.close()


def main():
    from confluent_kafka import Consumer, Producer
    from prometheus_client import Counter, start_http_server
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    start_http_server(METRICS_PORT)
    metrics = {"minutes": Counter("alert_check_minutes_total", "raw-signals minutes checked"),
               "alerts": Counter("alert_check_alerts_total", "alerts sent (SpO2 < threshold)")}
    consumer = Consumer({"bootstrap.servers": KAFKA, "group.id": GROUP,
                         "auto.offset.reset": env("OFFSET_RESET", "latest"),   # first start: old minutes are not urgent
                         "enable.auto.offset.store": False})
    producer = Producer({"bootstrap.servers": KAFKA, "enable.idempotence": True, "linger.ms": 0})
    stopping = []
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: stopping.append(1))
    log.info("alert-check: %s -> %s, SpO2 < %.0f %%, group %s", IN_TOPIC, OUT_TOPIC, ALERT_THRESHOLD, GROUP)
    try:
        run(consumer, producer, lambda: bool(stopping), metrics)
    except Exception:  # noqa: BLE001
        log.exception("alert-check crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
