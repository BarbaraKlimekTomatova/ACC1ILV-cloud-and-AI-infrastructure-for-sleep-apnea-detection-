"""apnea-detector (UC2, UC3 alert check, UC5). Owner: Barbara.

    python services/apnea-detector/detector.py

Three loops (threads) in one process:
  alerts    group apnea-alerts, NEVER paused (ADR 0002):
            raw-signals -> raw_nights row + alert if SpO2 < 80 % -> alerts, then saves the minute
  carbon    reads carbon-signal, keeps the newest mode (ADR 0003)
  analysis  group apnea-detector, paused in high_carbon while 08:00 is far:
            raw-signals -> NightFeatures + model -> apnea-events

The file has two halves:
  1. the logic (alert check, carbon rule, demo clock, models, analysis): no Kafka, no database,
     so the tests run without them
  2. Kafka, PostgreSQL (raw_nights), Prometheus metrics and the start

Kafka offsets are stored only after a message was handled (at least once).
Settings: environment variables, see README.md.
"""

import json
import logging
import math
import os
import signal
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np
from jsonschema import Draft202012Validator
from prometheus_client import Counter, Gauge, Histogram, start_http_server

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "common"))
import fast_model as FM  # noqa: E402   services/common/fast_model.py (Aliénor)
import features as F  # noqa: E402

# ---------------------------------------------------------------- settings
env = os.environ.get
KAFKA = env("KAFKA_BOOTSTRAP", "localhost:9092")                     # kafka:29092 inside Docker
DATABASE_URL = env("DATABASE_URL", "postgresql://apnea_detector:dev_apnea_detector@localhost:5432/sleep_apnea")
USE_DB = env("USE_DB", "1") == "1"
MODEL_PATH = env("MODEL_PATH", str(ROOT / "models" / "model.joblib"))
SCHEMA_DIR = Path(env("SCHEMA_DIR", str(ROOT / "kafka" / "schemas")))
DEFAULT_CARBON = {"mode": env("DEFAULT_CARBON_MODE", "low_carbon"),
                  "carbon_intensity": float(env("DEFAULT_CARBON_INTENSITY", "300")),
                  "region": None}
REGION = env("REGION") or None                                       # region of the node (AT / NO / PL)
DEMO_TIME = env("DEMO_TIME") or None                                 # e.g. 06:30, empty = real time
ALERT_THRESHOLD = float(env("ALERT_THRESHOLD", "80"))
MIN_VALID_SPO2 = float(env("MIN_VALID_SPO2", "50"))                  # lower = sensor artefact
DEADLINE = env("DEADLINE", "08:00")
DEADLINE_MARGIN_MIN = int(env("DEADLINE_MARGIN_MIN", "120"))
NIGHT_START = env("NIGHT_START", "20:00")                             # nights start after this time
TZ = ZoneInfo(env("TZ_DEADLINE", "Europe/Vienna"))
CPU_WATTS = float(env("CPU_WATTS", "15"))

ACCURATE, FAST, PAUSE = "accurate", "fast", "pause"
SPO2_LEN, BREATH_LEN = 60, 240                                        # one minute: 1 Hz and 4 Hz

log = logging.getLogger("apnea-detector")


# ================================================================ 1. LOGIC (no Kafka, no database)

# ---------------------------------------------------------------- clock (demo)
class Clock:
    """Local time for the carbon rule.

    DEMO_TIME=06:30 -> the detector starts as if it were 06:30 (Vienna) and the
    clock runs on from there. Lets the demo show the night (pause) and the
    morning (fast model) at any time of the day. Empty = real time.
    """

    def __init__(self, demo_time=None):
        self.offset = timedelta(0)
        if demo_time:
            real = datetime.now(TZ)
            h, m = (int(x) for x in demo_time.split(":"))
            fake = real.replace(hour=h, minute=m, second=0, microsecond=0)
            self.offset = fake - real

    def now(self):
        return datetime.now(TZ) + self.offset


# ---------------------------------------------------------------- alert check (UC3)
def spo2_min(values):
    """Lowest real SpO2 of the minute; null = drop-out, < 50 % = artefact. None if nothing valid."""
    ok = [v for v in values if v is not None and not math.isnan(v) and MIN_VALID_SPO2 <= v <= 100]
    return min(ok) if ok else None


def alert_for(raw):
    """raw-signals message -> alerts message, or None if SpO2 stayed >= 80 %."""
    low = spo2_min(raw["spo2"])
    if low is None or low >= ALERT_THRESHOLD:
        return None
    return {"patient_id": raw["patient_id"], "night_id": raw["night_id"],
            "minute": int(raw["minute"]), "spo2_min": round(float(low), 1),
            "threshold": ALERT_THRESHOLD, "detected_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------- carbon rule (UC5)
def decide(mode, now):
    """carbon mode + local time -> ACCURATE, FAST or PAUSE.

    low_carbon                   -> accurate model
    high_carbon, 08:00 is far    -> pause (the minutes wait in Kafka)
    high_carbon, 08:00 is close  -> fast model (close = DEADLINE_MARGIN_MIN, default 2 h)
    high_carbon, 08:00 is over   -> fast model: the night is already late, waiting for
                                    tomorrow's deadline would make it later (until NIGHT_START)
    """
    if mode == "low_carbon":
        return ACCURATE
    h, m = (int(x) for x in DEADLINE.split(":"))
    deadline = now.replace(hour=h, minute=m, second=0, microsecond=0)
    nh, nm = (int(x) for x in NIGHT_START.split(":"))
    night_start = now.replace(hour=nh, minute=nm, second=0, microsecond=0)
    if deadline <= now < night_start:
        return FAST                                  # late night (after 08:00): finish it now
    if deadline <= now:
        deadline += timedelta(days=1)                # evening -> tomorrow 08:00
    return FAST if deadline - now <= timedelta(minutes=DEADLINE_MARGIN_MIN) else PAUSE


# ---------------------------------------------------------------- models
class Model:
    """A file from services/model-trainer: {"model", "features", "classes", "version", "metrics"}."""

    def __init__(self, bundle, kind):
        if list(bundle["features"]) != list(F.FEATURES):
            raise ValueError(f"{kind} model was trained on other features, train it again")
        self.kind, self.model, self.version = kind, bundle["model"], bundle.get("version")
        self.columns = [bundle["classes"][int(c)] for c in self.model.classes_]

    @classmethod
    def load(cls, path, kind):
        return cls(joblib.load(path), kind)

    def predict(self, row):
        """features of one minute -> (event, probability of that event).
        accurate: apnea / hypopnea / normal. fast: apnea_or_hypopnea / normal."""
        p = dict(zip(self.columns, self.model.predict_proba(F.to_vector(row).reshape(1, -1))[0]))
        if self.kind == FAST:
            p_event = 1.0 - p.get("normal", 0.0)
            return ("apnea_or_hypopnea", p_event) if p_event >= 0.5 else ("normal", 1.0 - p_event)
        event = max(p, key=p.get)
        return event, p[event]


class RuleModel:
    """The fast model (ADR 0003): a rule without training, services/common/fast_model.py (Aliénor)."""

    kind, version = FAST, FM.VERSION

    def predict(self, row):
        return FM.predict(row)


def load_fast_model():
    """The fast model: the rule rule-v1 from services/common/fast_model.py (F1 0.832)."""
    return RuleModel()


# ---------------------------------------------------------------- analysis (UC2)
def to_array(values, length):
    """JSON list (null = drop-out) -> one FULL minute. The last minute of a night can be
    shorter: SpO2 is filled with NaN, breathing is mirrored (a flat line would look like an apnea)."""
    x = np.array([np.nan if v is None else v for v in values], np.float32)
    if len(x) >= length:
        return x[:length]
    if length == SPO2_LEN:
        return np.pad(x, (0, length - len(x)), constant_values=np.nan)
    return np.pad(np.nan_to_num(x), (0, length - len(x)), mode="symmetric")


class Analyzer:
    """One NightFeatures per night (the features need the last 5 minutes of the same night).
    Kafka key = patient_id, so all minutes of a night come to the same pod."""

    def __init__(self, accurate, fast=None, region=None):
        self.models = {ACCURATE: accurate, FAST: fast or accurate}
        self.region = region                         # region of the node (env REGION)
        self.nights = {}                             # night_id -> [NightFeatures, next minute, cpu s]

    def process(self, raw, action, carbon):
        """raw-signals message -> apnea-events message (None = minute already analysed).
        A pod that starts in the middle of a night begins with an empty history:
        the baselines are good again after 5 minutes."""
        night = self.nights.setdefault(raw["night_id"], [F.NightFeatures(), 0, 0.0])
        m = int(raw["minute"])
        if m < night[1]:
            return None                              # Kafka delivered it twice
        model = self.models[action]
        t0 = time.thread_time()
        row = night[0].add_minute(to_array(raw["spo2"], SPO2_LEN), to_array(raw["flow"], BREATH_LEN),
                                  to_array(raw["thorax"], BREATH_LEN), to_array(raw["abdomen"], BREATH_LEN))
        event, p = model.predict(row)
        night[1], night[2] = m + 1, night[2] + time.thread_time() - t0

        msg = {"patient_id": raw["patient_id"], "night_id": raw["night_id"], "minute": m,
               "event": event, "probability": round(float(p), 3),
               "model": model.kind, "model_version": model.version,
               "carbon_mode": "low_carbon" if action == ACCURATE else "high_carbon",
               "region": self.region or carbon.get("region"), "is_last": bool(raw["is_last"]),
               "sent_at": datetime.now(timezone.utc).isoformat()}
        if raw["is_last"]:
            # energy of the whole night: CPU seconds x CPU_WATTS (estimate), CO2 with the
            # carbon intensity of carbon-signal. CodeCarbon cannot measure millisecond steps.
            kwh = night[2] * CPU_WATTS / 3.6e6
            msg["kwh"] = round(kwh, 9)
            msg["gco2"] = round(kwh * (carbon.get("carbon_intensity") or 0.0), 6)
            del self.nights[raw["night_id"]]
        return msg


def encode(message):
    return json.dumps(message, separators=(",", ":")).encode()


# ================================================================ 2. KAFKA, DATABASE, METRICS
# confluent_kafka and psycopg are imported inside the functions, so the logic above
# (and its tests) also works where they are not installed.

# Prometheus metrics on :METRICS_PORT/metrics (UC6)
MINUTES = Counter("detector_minutes_total", "analysed minutes", ["model", "event"])
PAUSED = Gauge("detector_paused", "1 while the analysis waits for low carbon")
CARBON = Gauge("detector_carbon_intensity", "gCO2/kWh of the newest carbon-signal")
ALERTS = Counter("detector_alerts_total", "alerts sent")
GCO2 = Counter("detector_gco2_total", "gCO2 of the analysis (estimate)")
CONFIDENCE = Histogram("detector_confidence", "probability of the predicted event per minute (UC6 A1)",
                       ["model"], buckets=(0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0))

stop = threading.Event()
carbon = dict(DEFAULT_CARBON)            # newest carbon-signal, written by carbon_loop
carbon_known = threading.Event()         # set once we know the carbon mode of right now
RAW_SCHEMA = Draft202012Validator(json.loads((SCHEMA_DIR / "raw-signals-value.schema.json").read_text()))


# ---------------------------------------------------------------- table raw_nights
class RawNights:
    """Table raw_nights (db/init/02_raw_nights.sql), written only by the apnea-detector.

    Written by the alert loop, which is never paused:
      * the row is created at the FIRST minute, before any alert of the night,
        because alerts.night_id points to raw_nights,
      * then every minute is added, so the night is complete even while the
        analysis waits for low carbon.
    """

    SIGNALS = {"spo2": 60, "flow": 240, "thorax": 240, "abdomen": 240}   # values per minute

    def __init__(self, url):
        import psycopg
        self.conn = psycopg.connect(url)
        self.known = set()                  # nights whose row exists already

    def ensure_night(self, night_id, patient_id, source):
        if night_id in self.known:
            return
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO raw_nights (night_id, patient_id, source, spo2, flow, thorax, abdomen) "
                "VALUES (%s, %s, %s, '[]', '[]', '[]', '[]') ON CONFLICT (night_id) DO NOTHING",
                (night_id, patient_id, source))
        self.known.add(night_id)

    def append_minute(self, raw):
        """Add one minute. A minute that is already saved is skipped (Kafka can deliver
        twice); missing minutes before it are saved as null, so minute k stays at index k*60."""
        with self.conn.transaction():
            row = self.conn.execute("SELECT jsonb_array_length(spo2) FROM raw_nights "
                                    "WHERE night_id = %s FOR UPDATE", (raw["night_id"],)).fetchone()
            gap = int(raw["minute"]) - row[0] // self.SIGNALS["spo2"]
            if gap < 0:
                return False
            self.conn.execute(
                "UPDATE raw_nights SET " + ", ".join(f"{s} = {s} || %s::jsonb" for s in self.SIGNALS)
                + " WHERE night_id = %s",
                [json.dumps([None] * (gap * n) + list(raw[s])) for s, n in self.SIGNALS.items()]
                + [raw["night_id"]])
        return True


# ---------------------------------------------------------------- Kafka helpers
def consumer(group, **extra):
    from confluent_kafka import Consumer
    return Consumer({"bootstrap.servers": KAFKA, "group.id": group,
                     "auto.offset.reset": "earliest",        # a new group reads the nights that wait
                     "enable.auto.offset.store": False,      # offset stored after the work is done
                     **extra})


def read_raw(msg):
    """Kafka message -> valid raw-signals dict, or None (logged and skipped)."""
    try:
        raw = json.loads(msg.value())
        RAW_SCHEMA.validate(raw)
        return raw
    except Exception as e:  # noqa: BLE001  one bad message must not stop the detector
        log.error("bad raw-signals message at offset %s: %s", msg.offset(), str(e)[:200])
        return None


# ---------------------------------------------------------------- alerts loop (UC3)
def alert_loop(producer, db):
    c = consumer("apnea-alerts")
    c.subscribe(["raw-signals"])
    while not stop.is_set():
        msg = c.poll(1.0)
        if msg is None or msg.error():
            continue
        raw = read_raw(msg)
        if raw:
            handle_alert_minute(raw, producer, db)
        c.store_offsets(msg)
    c.close()


def handle_alert_minute(raw, producer, db):
    """1. raw_nights row (FK of alerts)  2. alert right away  3. save the minute.
    If the database is down, the alert still goes out."""
    if db:
        try:
            db.ensure_night(raw["night_id"], raw["patient_id"], raw["source"])
        except Exception:  # noqa: BLE001
            log.exception("raw_nights row for %s", raw["night_id"])
    alert = alert_for(raw)
    if alert:
        producer.produce("alerts", key=raw["patient_id"], value=encode(alert))
        producer.flush(5)
        ALERTS.inc()
        log.info("ALERT %s minute %s SpO2 %s", raw["night_id"], raw["minute"], alert["spo2_min"])
    if db:
        try:
            db.append_minute(raw)
        except Exception:  # noqa: BLE001
            log.exception("saving minute %s of %s", raw["minute"], raw["night_id"])


# ---------------------------------------------------------------- carbon-signal loop (UC5)
def carbon_loop():
    """Start at the newest carbon-signal message (= the mode right now), then follow the topic."""
    from confluent_kafka import OFFSET_END, TopicPartition
    c = consumer("apnea-detector-carbon", **{"enable.auto.commit": False})
    parts = []
    for p in c.list_topics("carbon-signal", timeout=10).topics["carbon-signal"].partitions:
        low, high = c.get_watermark_offsets(TopicPartition("carbon-signal", p), timeout=10)
        parts.append(TopicPartition("carbon-signal", p, high - 1 if high > low else OFFSET_END))
    if all(tp.offset == OFFSET_END for tp in parts):
        carbon_known.set()                   # topic empty: DEFAULT_CARBON_MODE until the first message
    c.assign(parts)
    while not stop.is_set():
        msg = c.poll(1.0)
        if msg is None or msg.error():
            continue
        try:
            sig = json.loads(msg.value())
            sig["mode"], sig["carbon_intensity"], sig["region"]
        except Exception:  # noqa: BLE001
            log.error("bad carbon-signal message: %r", msg.value()[:200])
            continue
        carbon.update(mode=sig["mode"], carbon_intensity=sig["carbon_intensity"], region=sig["region"])
        carbon_known.set()
        CARBON.set(sig["carbon_intensity"])
        log.info("carbon mode %s (%s, %.0f g/kWh)", sig["mode"], sig["region"], sig["carbon_intensity"])
    c.close()


# ---------------------------------------------------------------- analysis loop (UC2)
def analysis_loop(producer, analyzer, clock):
    from confluent_kafka import TopicPartition
    carbon_known.wait(30)                    # never analyse before we know the carbon mode
    c = consumer("apnea-detector")
    c.subscribe(["raw-signals"])
    paused = False
    while not stop.is_set():
        action = decide(carbon["mode"], clock.now())
        if action == PAUSE:
            if not paused:
                log.info("high carbon and %s is far: analysis paused", DEADLINE)
            c.pause(c.assignment())          # every loop, so also new partitions after a rebalance
        elif paused:
            c.resume(c.assignment())
            log.info("analysis resumed with the %s model", action)
        paused = action == PAUSE
        PAUSED.set(paused)

        msg = c.poll(1.0)                    # keeps the consumer in the group while paused
        if msg is None or msg.error():
            continue
        if paused:
            # from a partition assigned during this poll: put it back for later
            c.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
            c.pause(c.assignment())
            continue
        raw = read_raw(msg)
        out = analyzer.process(raw, action, carbon) if raw else None
        if out:
            producer.produce("apnea-events", key=raw["patient_id"], value=encode(out))
            producer.poll(0)
            MINUTES.labels(out["model"], out["event"]).inc()
            CONFIDENCE.labels(out["model"]).observe(out["probability"])
            if out["is_last"]:
                GCO2.inc(out["gco2"])
                log.info("night %s done (%d minutes)", raw["night_id"], out["minute"] + 1)
        c.store_offsets(msg)
    producer.flush(10)
    c.close()


# ---------------------------------------------------------------- start
def main():
    from confluent_kafka import Producer
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    start_http_server(int(env("METRICS_PORT", "8000")))
    accurate = Model.load(MODEL_PATH, ACCURATE)
    fast = load_fast_model()
    clock = Clock(DEMO_TIME)
    log.info("models: accurate %s, fast %s; local time %s%s", accurate.version, fast.version,
             clock.now().strftime("%H:%M"), " (DEMO_TIME)" if DEMO_TIME else "")

    producer = Producer({"bootstrap.servers": KAFKA, "linger.ms": 5, "enable.idempotence": True})
    analyzer = Analyzer(accurate, fast, REGION)
    failed = threading.Event()

    def run(target, *args):
        """If one loop crashes, stop the whole pod so Kubernetes restarts it."""
        def wrapper():
            try:
                target(*args)
            except Exception:  # noqa: BLE001
                log.exception("%s crashed", target.__name__)
                failed.set()
                stop.set()
        return threading.Thread(target=wrapper, name=target.__name__)

    threads = [run(alert_loop, producer, RawNights(DATABASE_URL) if USE_DB else None),
               run(carbon_loop),
               run(analysis_loop, producer, analyzer, clock)]
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: stop.set())
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    sys.exit(1 if failed.is_set() else 0)


if __name__ == "__main__":
    main()
