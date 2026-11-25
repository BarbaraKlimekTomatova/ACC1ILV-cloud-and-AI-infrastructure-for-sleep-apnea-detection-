"""ahi-triage (UC2 steps 6-10). Owner: Barbara.

    python services/ahi-triage/ahi_triage.py

Reads apnea-events (one message per minute of a night, sent by the apnea-detector),
counts the events of each night and, at the last minute (is_last):
  * AHI = minutes with an event / hours of recording
  * severity: < 5 normal, 5-15 mild, 15-30 moderate, >= 30 severe
  * deadline_met = finished before 08:00 (Europe/Vienna)
  * saves one row in the table results and sends night-results

The file has two halves:
  1. the logic (counting, AHI, severity, deadline, messages): no Kafka, no database,
     so the tests run without them
  2. Kafka, PostgreSQL (results), Prometheus metrics and the start

Restart during a night (UC2 A3): the counts are kept in memory, so a Kafka offset is
stored only when every night that started at or before it is saved in results. After a
restart the unfinished nights are read again from Kafka; a night that is already in
results is not saved or sent twice.

LLM summary (UC2 step 8, ADR 0009): two sentences for the doctor from a small LOCAL model
(Ollama, like course exercise 7), so no patient data leaves our system. The prompt has only
numbers, no patient id or name. CO2 of the call = Ollama's run time x LLM_WATTS x the carbon
intensity of the night (ADR 0010). If the LLM does not answer, the result is saved without
summary (UC2 A4).
"""

import json
import logging
import os
import signal
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator
from prometheus_client import Counter, Gauge, Histogram, start_http_server

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- settings
env = os.environ.get
KAFKA = env("KAFKA_BOOTSTRAP", "localhost:9092")                     # kafka:29092 inside Docker
DATABASE_URL = env("DATABASE_URL", "postgresql://ahi_triage:dev_ahi_triage@localhost:5432/sleep_apnea")
USE_DB = env("USE_DB", "1") == "1"
SCHEMA_DIR = Path(env("SCHEMA_DIR", str(ROOT / "kafka" / "schemas")))
DEADLINE = env("DEADLINE", "08:00")
TZ = ZoneInfo(env("TZ_DEADLINE", "Europe/Vienna"))
DEMO_TIME = env("DEMO_TIME") or None                                 # same demo clock as the detector
USE_LLM = env("USE_LLM", "1") == "1"                                 # 0 = no summary
LLM_URL = env("LLM_URL", "http://localhost:11434")                   # Ollama; host.docker.internal:11434 from Docker
LLM_MODEL = env("LLM_MODEL", "llama3.2:1b")                          # small model, ~1.3 GB
LLM_TIMEOUT_S = float(env("LLM_TIMEOUT_S", "60"))
LLM_WATTS = float(env("LLM_WATTS", "30"))                            # power of the machine running Ollama (estimate)
DEFAULT_CARBON_INTENSITY = float(env("DEFAULT_CARBON_INTENSITY", "300"))  # gCO2/kWh if the night has none

EVENTS = ("apnea", "hypopnea", "apnea_or_hypopnea")                  # "normal" is not an event
SEVERITY = ((5, "normal"), (15, "mild"), (30, "moderate"))           # AHI below the limit -> name

log = logging.getLogger("ahi-triage")


# ================================================================ 1. LOGIC (no Kafka, no database)

class Clock:
    """Local time; DEMO_TIME=06:30 starts the clock at 06:30 (Vienna), like in the detector."""

    def __init__(self, demo_time=None):
        self.offset = timedelta(0)
        if demo_time:
            real = datetime.now(TZ)
            h, m = (int(x) for x in demo_time.split(":"))
            self.offset = real.replace(hour=h, minute=m, second=0, microsecond=0) - real

    def now(self):
        return datetime.now(TZ) + self.offset


def next_deadline(start):
    """The first 08:00 (local) after the night started."""
    h, m = (int(x) for x in DEADLINE.split(":"))
    d = start.replace(hour=h, minute=m, second=0, microsecond=0)
    return d if d > start else d + timedelta(days=1)


def severity(ahi):
    for limit, name in SEVERITY:
        if ahi < limit:
            return name
    return "severe"


class Night:
    """Counts of one night. Every minute is counted once (Kafka delivers at least once)."""

    def __init__(self, started):
        self.started = started                 # local time of the first message
        self.events = {}                       # minute -> event
        self.last = None                       # the is_last message

    def add(self, msg):
        self.events[int(msg["minute"])] = msg["event"]
        if msg["is_last"]:
            self.last = msg

    def result(self, finished):
        """-> night-results message (the results row has the same values)."""
        last = self.last
        minutes = max(self.events) + 1                       # the recording, missing minutes included
        apnea = sum(e == "apnea" for e in self.events.values())
        hypopnea = sum(e == "hypopnea" for e in self.events.values())
        events = sum(e in EVENTS for e in self.events.values())
        ahi = round(events / (minutes / 60), 1)
        fast = last["model"] == "fast"                       # fast model: no apnea/hypopnea split
        return {
            "patient_id": last["patient_id"],
            "night_id": last["night_id"],
            "ahi": ahi,
            "severity": severity(ahi),
            "event_count": events,
            "apnea_count": None if fast else apnea,
            "hypopnea_count": None if fast else hypopnea,
            "minutes": minutes,
            "model": last["model"],
            "model_version": last.get("model_version"),
            "carbon_mode": last["carbon_mode"],
            "region": last.get("region"),
            "kwh": last.get("kwh"),
            "gco2": last.get("gco2"),
            "deadline_met": finished <= next_deadline(self.started),
            "finished_at": finished.astimezone(timezone.utc).isoformat(),
        }


class Offsets:
    """Which Kafka offset may be stored per partition (UC2 A3).

    The offset of a partition may only move past a message when its night is saved.
    So it stays at the first message of the oldest unfinished night of that partition.
    """

    def __init__(self):
        self.first = {}                        # (partition, night_id) -> first offset
        self.last = {}                         # partition -> last handled offset

    def seen(self, partition, offset, night_id):
        self.first.setdefault((partition, night_id), offset)
        self.last[partition] = offset

    def done(self, partition, night_id):
        self.first.pop((partition, night_id), None)

    def safe(self, partition):
        """The offset to store (= the next message to read after a restart), or None."""
        open_ = [o for (p, _), o in self.first.items() if p == partition]
        if open_:
            return min(open_)
        last = self.last.get(partition)
        return None if last is None else last + 1


class Triage:
    """All nights in progress. handle() -> night-results message when a night is complete."""

    def __init__(self, clock=None, already_saved=None):
        self.clock = clock or Clock()
        self.nights = {}
        self.finished = set()                  # nights done in this process
        self.already_saved = already_saved or (lambda night_id: False)

    def is_finished(self, night_id):
        return night_id in self.finished

    def handle(self, msg):
        nid = msg["night_id"]
        if nid in self.finished:               # a late duplicate of a finished night
            return None
        night = self.nights.get(nid)
        if night is None:
            night = self.nights[nid] = Night(self.clock.now())
        night.add(msg)
        if night.last is None:
            return None
        del self.nights[nid]
        self.finished.add(nid)
        if self.already_saved(nid):            # read again after a restart
            log.info("night %s is already in results, skipped", nid)
            return None
        return night.result(self.clock.now())


# ---------------------------------------------------------------- LLM summary (UC2 step 8)
def llm_prompt(result):
    """The prompt for the LLM. Only numbers of the night: no patient id, no name (GDPR).
    A small model is good at wording, not at deciding, so the urgency is decided here."""
    if result.get("apnea_count") is None:                 # fast model: no apnea/hypopnea split
        events = f"- minutes with apnea or hypopnea: {result['event_count']}"
    else:
        events = (f"- minutes with apnea: {result['apnea_count']}, "
                  f"minutes with hypopnea: {result['hypopnea_count']}")
    urgency = "review soon" if result["severity"] in ("moderate", "severe") else "routine review"
    return ("Facts about one night of a home sleep apnea screening:\n"
            f"- recording: {result['minutes'] / 60:.1f} hours\n"
            f"- AHI: {result['ahi']} events per hour\n"
            f"- severity: {result['severity']}\n"
            f"{events}\n\n"
            "Write exactly 2 sentences for the sleep doctor. Sentence 1: repeat the AHI and the "
            f"severity. Sentence 2: say how urgent a review is ({urgency}). Use only the facts above. "
            "No greeting, no title, no diagnosis, no therapy.")


def night_carbon_intensity(result):
    """gCO2/kWh of the night, from the detector's kwh and gco2 (ADR 0010)."""
    kwh, gco2 = result.get("kwh"), result.get("gco2")
    return gco2 / kwh if kwh and gco2 is not None else DEFAULT_CARBON_INTENSITY


def ollama_generate(prompt, url=None, model=None, timeout=None):
    """One call to Ollama's /api/generate (no streaming) -> its JSON answer."""
    body = json.dumps({"model": model or LLM_MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0, "num_predict": 120}}).encode()
    req = urllib.request.Request(f"{url or LLM_URL}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout or LLM_TIMEOUT_S) as r:
        return json.loads(r.read())


def add_summary(result, generate=ollama_generate):
    """result + llm_summary, llm_model, llm_gco2. If the LLM fails: all three None (UC2 A4)."""
    t0 = time.monotonic()
    try:
        answer = generate(llm_prompt(result))
        text = answer["response"].strip()
        if not text:
            raise ValueError("empty answer")
    except Exception as e:  # noqa: BLE001  no summary must not stop the result
        log.warning("no LLM summary for %s: %s", result["night_id"], str(e)[:200])
        return {**result, "llm_summary": None, "llm_model": None, "llm_gco2": None}
    seconds = answer.get("total_duration", 0) / 1e9 or (time.monotonic() - t0)   # Ollama gives ns
    kwh = seconds * LLM_WATTS / 3.6e6
    return {**result, "llm_summary": text, "llm_model": LLM_MODEL,
            "llm_gco2": round(kwh * night_carbon_intensity(result), 6)}


# ================================================================ 2. KAFKA, DATABASE, METRICS
# confluent_kafka and psycopg are imported inside the functions, so the logic above
# (and its tests) also works where they are not installed.

NIGHTS = Counter("triage_nights_total", "finished nights", ["severity"])
AHI = Histogram("triage_ahi", "AHI of finished nights", buckets=(5, 15, 30, 45, 60, 90))
OPEN = Gauge("triage_open_nights", "nights in progress")
DEADLINE_MISSED = Counter("triage_deadline_missed_total", "nights finished after 08:00")
BAD_MESSAGES = Counter("triage_bad_messages_total", "apnea-events that failed the schema")
LLM_FAILED = Counter("triage_llm_failed_total", "nights saved without LLM summary (UC2 A4)")
LLM_GCO2 = Counter("triage_llm_gco2_total", "gCO2 of the LLM summaries (estimate)")

stop = threading.Event()
EVENTS_SCHEMA = Draft202012Validator(json.loads((SCHEMA_DIR / "apnea-events-value.schema.json").read_text()))


class Results:
    """Table results (db/init/03_results.sql), written only by ahi-triage."""

    COLUMNS = ("night_id", "ahi", "severity", "event_count", "model", "model_version", "carbon_mode",
               "region", "kwh", "gco2", "deadline_met", "llm_summary", "llm_model", "llm_gco2")

    def __init__(self, url):
        import psycopg
        self.conn = psycopg.connect(url, autocommit=True)

    def exists(self, night_id):
        return self.conn.execute("SELECT 1 FROM results WHERE night_id = %s LIMIT 1",
                                 (night_id,)).fetchone() is not None

    def save(self, result):
        # fixed SQL text (psycopg wants a literal string), same column order as COLUMNS
        self.conn.execute(
            "INSERT INTO results (night_id, ahi, severity, event_count, model, model_version, carbon_mode, "
            "region, kwh, gco2, deadline_met, llm_summary, llm_model, llm_gco2) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [result.get(c) for c in self.COLUMNS])


def loop(db):
    from confluent_kafka import Consumer, Producer, TopicPartition
    c = Consumer({"bootstrap.servers": KAFKA, "group.id": "ahi-triage",
                  "auto.offset.reset": "earliest",
                  "enable.auto.offset.store": False})       # we store the safe offset ourselves
    producer = Producer({"bootstrap.servers": KAFKA, "enable.idempotence": True})
    triage = Triage(Clock(DEMO_TIME), db.exists if db else None)
    offsets = Offsets()
    c.subscribe(["apnea-events"])
    log.info("reading apnea-events (group ahi-triage)")
    while not stop.is_set():
        msg = c.poll(1.0)
        if msg is None or msg.error():
            continue
        p = msg.partition()
        try:
            event = json.loads(msg.value())
            EVENTS_SCHEMA.validate(event)
        except Exception as e:  # noqa: BLE001  one bad message must not stop the service
            BAD_MESSAGES.inc()
            log.error("bad apnea-events message at offset %s: %s", msg.offset(), str(e)[:200])
            offsets.seen(p, msg.offset(), f"bad-{msg.offset()}")
            offsets.done(p, f"bad-{msg.offset()}")
        else:
            offsets.seen(p, msg.offset(), event["night_id"])
            if triage.is_finished(event["night_id"]):         # duplicate: nothing waits for it
                offsets.done(p, event["night_id"])
            result = triage.handle(event)
            if result is not None:
                if USE_LLM:
                    result = add_summary(result)       # takes a few seconds, the offset waits for it
                    if result["llm_summary"] is None:
                        LLM_FAILED.inc()
                    else:
                        LLM_GCO2.inc(result["llm_gco2"])
                if db:
                    db.save(result)                    # a DB error stops the pod; Kafka keeps the night
                producer.produce("night-results", key=result["patient_id"],
                                 value=json.dumps(result).encode())
                producer.flush(5)
                NIGHTS.labels(result["severity"]).inc()
                AHI.observe(result["ahi"])
                if not result["deadline_met"]:
                    DEADLINE_MISSED.inc()
                log.info("night %s: AHI %.1f %s (%d events in %d minutes)", result["night_id"],
                         result["ahi"], result["severity"], result["event_count"], result["minutes"])
            if event["is_last"]:
                offsets.done(p, event["night_id"])
        OPEN.set(len(triage.nights))
        safe = offsets.safe(p)
        if safe is not None:
            c.store_offsets(offsets=[TopicPartition(msg.topic(), p, safe)])
    producer.flush(10)
    c.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    start_http_server(int(env("METRICS_PORT", "8001")))
    db = Results(DATABASE_URL) if USE_DB else None
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: stop.set())
    loop(db)


if __name__ == "__main__":
    main()
