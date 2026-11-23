"""alert-service (UC3, ADR 0002). Owner: Aliénor.

    python services/alert-service/alert_service.py

Reads the `alerts` topic (sent by alert-check) with its own consumer group and inserts every
alert into the `alerts` table (db/init/05_alerts.sql) as the database user `alert_service`
(ADR 0007: it may only INSERT into `alerts`). The doctor-dashboard shows the rows.

  * detected_at = when alert-check saw the drop, stored_at = now() in the database,
    so  stored_at - detected_at  is the alert latency (SLO < 5 s, also in /metrics).
  * Kafka can deliver a message twice (and the detector's own alert loop can send the same
    alert): a second alert for the same night and minute is skipped, not stored twice.
  * alerts.night_id points to raw_nights. That row is created by the apnea-detector's
    never-paused loop at the first minute of the night. If it is not there yet, the insert
    is retried for FK_WAIT_S seconds; after that the alert is logged as an ERROR, counted in
    alert_service_dropped_total and skipped, so one broken night cannot block all other alerts.

The file has two halves:
  1. the logic (message check, SQL, retry): no Kafka, the database is passed in
  2. Kafka, PostgreSQL, Prometheus metrics and the start

Offsets are stored only after the row is in the database (at least once).
Settings: environment variables, see README.md.
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- settings
env = os.environ.get
KAFKA = env("KAFKA_BOOTSTRAP", "localhost:9092")                     # kafka:29092 inside Docker
GROUP = env("GROUP_ID", "alert-service")
TOPIC = env("TOPIC", "alerts")
DATABASE_URL = env("DATABASE_URL", "postgresql://alert_service:dev_alert_service@localhost:5432/sleep_apnea")
SCHEMA_DIR = Path(env("SCHEMA_DIR", str(ROOT / "kafka" / "schemas")))
FK_WAIT_S = float(env("FK_WAIT_S", "60"))                            # wait for the raw_nights row
RETRY_S = float(env("RETRY_S", "1"))
METRICS_PORT = int(env("METRICS_PORT", "8003"))

log = logging.getLogger("alert-service")
ALERT_SCHEMA = Draft202012Validator(json.loads((SCHEMA_DIR / "alerts-value.schema.json").read_text()))

# skip the alert if the same night + minute is already stored (no UNIQUE constraint in the table,
# and alert_service may read every table, so WHERE NOT EXISTS works without a schema change)
INSERT_SQL = """
INSERT INTO alerts (night_id, minute, spo2_min, detected_at)
SELECT %(night_id)s, %(minute)s, %(spo2_min)s, %(detected_at)s
WHERE NOT EXISTS (SELECT 1 FROM alerts WHERE night_id = %(night_id)s AND minute = %(minute)s)
RETURNING alert_id, stored_at
"""


# ================================================================ 1. LOGIC

def parse_alert(value):
    """Kafka value -> valid alerts dict, or None (a bad message is logged and skipped)."""
    try:
        alert = json.loads(value)
        ALERT_SCHEMA.validate(alert)
        alert["detected_at_dt"] = datetime.fromisoformat(alert["detected_at"].replace("Z", "+00:00"))
        return alert
    except Exception as e:  # noqa: BLE001  one bad message must not stop the service
        log.error("bad alerts message: %s", str(e)[:200])
        return None


def row_params(alert):
    return {"night_id": alert["night_id"], "minute": alert["minute"],
            "spo2_min": alert["spo2_min"], "detected_at": alert["detected_at_dt"]}


class MissingNight(Exception):
    """The raw_nights row of this alert does not exist (yet)."""


def store(db, alert, fk_wait_s=FK_WAIT_S, retry_s=RETRY_S, sleep=time.sleep, clock=time.monotonic):
    """Insert one alert. Returns "stored", "duplicate" or "dropped" (raw_nights row never came).
    `db.insert(params)` returns (alert_id, stored_at) or None for a duplicate,
    and raises MissingNight on a foreign key error."""
    give_up = clock() + fk_wait_s
    while True:
        try:
            row = db.insert(row_params(alert))
            return "duplicate" if row is None else ("stored", row)
        except MissingNight:
            if clock() >= give_up:
                return "dropped"
            sleep(retry_s)


def latency_s(detected_at, stored_at):
    return max(0.0, (stored_at - detected_at).total_seconds())


# ================================================================ 2. KAFKA, DATABASE, METRICS, START

class AlertsTable:
    """Table alerts, written only by alert-service (INSERT only, ADR 0007). Reconnects when needed."""

    def __init__(self, url):
        self.url, self.conn = url, None

    def _connect(self):
        import psycopg
        if self.conn is None or self.conn.closed:
            self.conn = psycopg.connect(self.url, autocommit=True)
        return self.conn

    def insert(self, params):
        import psycopg
        for attempt in range(2):
            try:
                return self._connect().execute(INSERT_SQL, params).fetchone()
            except psycopg.errors.ForeignKeyViolation as e:
                raise MissingNight(params["night_id"]) from e
            except psycopg.OperationalError:
                self.conn = None                          # database restarted: connect again once
                if attempt:
                    raise
                time.sleep(RETRY_S)


def run(consumer, db, stop, metrics=None):
    consumer.subscribe([TOPIC])
    while not stop():
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        alert = parse_alert(msg.value())
        if alert:
            result = store(db, alert)
            if result == "dropped":
                log.error("alert %s minute %s NOT stored: no raw_nights row after %.0f s "
                          "(is the apnea-detector running?)", alert["night_id"], alert["minute"], FK_WAIT_S)
                if metrics:
                    metrics["dropped"].inc()
            elif result == "duplicate":
                log.info("alert %s minute %s already stored, skipped", alert["night_id"], alert["minute"])
                if metrics:
                    metrics["duplicates"].inc()
            else:
                alert_id, stored_at = result[1]
                lat = latency_s(alert["detected_at_dt"], stored_at)
                log.info("stored alert %s: %s minute %s SpO2 %.1f %% (latency %.2f s)",
                         alert_id, alert["night_id"], alert["minute"], alert["spo2_min"], lat)
                if metrics:
                    metrics["stored"].inc()
                    metrics["latency"].observe(lat)
        consumer.store_offsets(msg)
    consumer.close()


def main():
    from confluent_kafka import Consumer
    from prometheus_client import Counter, Histogram, start_http_server
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    start_http_server(METRICS_PORT)
    metrics = {
        "stored": Counter("alert_service_alerts_stored_total", "alerts written to the alerts table"),
        "duplicates": Counter("alert_service_duplicates_total", "alerts skipped, same night and minute"),
        "dropped": Counter("alert_service_dropped_total", "alerts not stored: no raw_nights row"),
        "latency": Histogram("alert_service_latency_seconds", "stored_at - detected_at (SLO < 5 s)",
                             buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30)),
    }
    consumer = Consumer({"bootstrap.servers": KAFKA, "group.id": GROUP,
                         "auto.offset.reset": "earliest",          # an alert must never be lost
                         "enable.auto.offset.store": False})
    stopping = []
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: stopping.append(1))
    log.info("alert-service: %s -> table alerts, group %s", TOPIC, GROUP)
    try:
        run(consumer, AlertsTable(DATABASE_URL), lambda: bool(stopping), metrics)
    except Exception:  # noqa: BLE001
        log.exception("alert-service crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
