"""carbon-scheduler (UC5, ADR 0003, ADR 0004). Owner: Aliénor.

    python services/carbon-scheduler/carbon_scheduler.py                  # real time
    SPEED=60 START_TIME=22:00 python services/carbon-scheduler/carbon_scheduler.py   # demo: 1 s = 1 min
    FORCE_MODE=high_carbon python services/carbon-scheduler/carbon_scheduler.py     # demo: always dirty

Simulates the carbon intensity (gCO2/kWh) of three regions and tells the other services
where and how to run, on the Kafka topic `carbon-signal`
(kafka/schemas/carbon-signal-value.schema.json, key = region):

    {"region": "NO", "carbon_intensity": 31.2, "mode": "low_carbon", "sent_at": "..."}

Simulated intensity (a daily curve + a little noise, or a CSV with CARBON_CSV):
    NO   hydro power, 20 - 40, always clean
    AT   hydro + gas, 120 at 13:00 (sun) - 380 at 01:00 (gas at night)
    PL   coal, 550 at 13:00 - 750 at 01:00, always dirty

Every STEP_S seconds:
  1. read the intensity of every region (REGIONS, default AT,NO,PL)
  2. region: stay, unless another region is cleaner by more than MOVE_THRESHOLD (20 %) and the
     last move was at least MIN_MOVE_MINUTES (15) simulated minutes ago (ADR 0004, no ping-pong)
  3. mode: high_carbon if the intensity of that region is above HIGH_CARBON_THRESHOLD (300)
  4. send carbon-signal when the region or the mode changes, or the intensity moved by more
     than RESEND_PCT (10 %) since the last message (the detector uses it for the gCO2 of a night)
  5. log the decision in the table carbon_decisions (pause / resume / move), as DB user
     carbon_scheduler (ADR 0007). USE_DB=0 = no database.

With NO in REGIONS the cleanest region is always NO, so the mode is always low_carbon.
To show high_carbon in the demo: REGIONS=AT,PL (AT is dirty at night) or FORCE_MODE=high_carbon.

Moving the detector pod itself (patching nodeAffinity in Kubernetes) is not done here yet;
the detector already writes the region of carbon-signal into apnea-events / results.

The file has two halves:
  1. the logic (clock, intensity, decision): no Kafka, no database, so the tests run without them
  2. Kafka, PostgreSQL, Prometheus metrics and the start
"""

import csv
import json
import logging
import math
import os
import random
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- settings
env = os.environ.get
KAFKA = env("KAFKA_BOOTSTRAP", "localhost:9092")                     # kafka:29092 inside Docker
TOPIC = env("TOPIC", "carbon-signal")
DATABASE_URL = env("DATABASE_URL", "postgresql://carbon_scheduler:dev_carbon_scheduler@localhost:5432/sleep_apnea")
USE_DB = env("USE_DB", "1") == "1"
SCHEMA_DIR = Path(env("SCHEMA_DIR", str(ROOT / "kafka" / "schemas")))
TZ = ZoneInfo(env("TZ_LOCAL", "Europe/Vienna"))

REGIONS = [r.strip() for r in env("REGIONS", "AT,NO,PL").split(",") if r.strip()]
HIGH_CARBON_THRESHOLD = float(env("HIGH_CARBON_THRESHOLD", "300"))  # gCO2/kWh
MOVE_THRESHOLD = float(env("MOVE_THRESHOLD", "0.2"))                 # other region 20 % cleaner
MIN_MOVE_MINUTES = float(env("MIN_MOVE_MINUTES", "15"))              # simulated minutes between moves
RESEND_PCT = float(env("RESEND_PCT", "10"))
FORCE_MODE = env("FORCE_MODE") or None                               # low_carbon / high_carbon / empty
CARBON_CSV = env("CARBON_CSV") or None                               # columns: time (HH:MM), AT, NO, PL
NOISE_PCT = float(env("NOISE_PCT", "3"))
SEED = int(env("SEED", "42"))

STEP_S = float(env("STEP_S", "5"))                                   # real seconds between readings
SPEED = float(env("SPEED", "1"))                                     # simulated seconds per real second
START_TIME = env("START_TIME") or None                               # HH:MM, empty = now
METRICS_PORT = int(env("METRICS_PORT", "8004"))

LOW, HIGH = "low_carbon", "high_carbon"
log = logging.getLogger("carbon-scheduler")
SIGNAL_SCHEMA = Draft202012Validator(json.loads((SCHEMA_DIR / "carbon-signal-value.schema.json").read_text()))


# ================================================================ 1. LOGIC (no Kafka, no database)

class SimClock:
    """Simulated local time: starts at START_TIME (or now) and runs SPEED times faster."""

    def __init__(self, start_time=None, speed=1.0, real=time.monotonic):
        self.real, self.speed, self.t0 = real, speed, real()
        now = datetime.now(TZ)
        if start_time:
            h, m = (int(x) for x in start_time.split(":"))
            now = now.replace(hour=h, minute=m, second=0, microsecond=0)
        self.start = now

    def now(self):
        return self.start + timedelta(seconds=(self.real() - self.t0) * self.speed)


# daily curve per region: (mean, swing, hour of the peak). Peak at night, low at 13:00 (sun).
PROFILES = {
    "NO": (30.0, 10.0, 1.0),
    "AT": (250.0, 130.0, 1.0),
    "PL": (650.0, 100.0, 1.0),
}


def curve(region, when):
    """Intensity without noise at local time `when` (a datetime)."""
    mean, swing, peak = PROFILES[region]
    hour = when.hour + when.minute / 60 + when.second / 3600
    return mean + swing * math.cos(2 * math.pi * (hour - peak) / 24)


class Simulated:
    """Daily curve + a little noise (seeded, so a demo can be repeated)."""

    def __init__(self, regions, noise_pct=NOISE_PCT, seed=SEED):
        unknown = set(regions) - set(PROFILES)
        if unknown or not regions:
            raise ValueError(f"unknown regions {sorted(unknown)}, use AT, NO, PL")
        self.regions, self.noise, self.rng = regions, noise_pct / 100, random.Random(seed)

    def read(self, when):
        return {r: round(max(0.0, curve(r, when) * (1 + self.rng.uniform(-self.noise, self.noise))), 1)
                for r in self.regions}


class CsvReplay:
    """CSV replay: one row per time of day (HH:MM), a column per region, linear in between."""

    def __init__(self, path, regions):
        self.regions, self.rows = regions, []
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                h, m = (int(x) for x in r["time"].split(":"))
                self.rows.append((h * 60 + m, {g: float(r[g]) for g in regions}))
        self.rows.sort(key=lambda x: x[0])
        if not self.rows:
            raise ValueError(f"{path} has no rows")

    def read(self, when):
        t = when.hour * 60 + when.minute + when.second / 60
        rows = self.rows + [(self.rows[0][0] + 1440, self.rows[0][1])]     # wrap around midnight
        if t < rows[0][0]:
            t += 1440
        for (t1, a), (t2, b) in zip(rows, rows[1:]):
            if t1 <= t <= t2:
                w = 0 if t2 == t1 else (t - t1) / (t2 - t1)
                return {g: round(a[g] + w * (b[g] - a[g]), 1) for g in self.regions}
        return dict(self.rows[-1][1])


class Scheduler:
    """Decides region and mode from the intensities; remembers the last move and the last message."""

    def __init__(self, threshold=HIGH_CARBON_THRESHOLD, move_threshold=MOVE_THRESHOLD,
                 min_move_minutes=MIN_MOVE_MINUTES, resend_pct=RESEND_PCT, force_mode=FORCE_MODE):
        if force_mode not in (None, LOW, HIGH):
            raise ValueError(f"FORCE_MODE must be {LOW}, {HIGH} or empty, not {force_mode!r}")
        self.threshold, self.move_threshold = threshold, move_threshold
        self.min_move = timedelta(minutes=min_move_minutes)
        self.resend, self.force = resend_pct / 100, force_mode
        self.region = self.mode = self.last_move = self.last_sent = None

    def step(self, intensities, now):
        """intensities {region: g/kWh} + simulated time -> (message or None, decisions).
        decisions = rows for carbon_decisions: dicts with action, region, carbon_intensity, reason."""
        best = min(intensities, key=intensities.get)
        decisions = []

        # ---- region (ADR 0004)
        if self.region is None or self.region not in intensities:
            self.region, self.last_move = best, now
        elif best != self.region:
            cur, new = intensities[self.region], intensities[best]
            cleaner = cur > 0 and (cur - new) / cur > self.move_threshold
            waited = now - self.last_move >= self.min_move
            if cleaner and waited:
                decisions.append({"action": "move", "region": best, "carbon_intensity": new,
                                  "reason": f"{best} {new:.0f} is {100 * (cur - new) / cur:.0f} % cleaner "
                                            f"than {self.region} {cur:.0f}"})
                self.region, self.last_move = best, now

        # ---- mode (ADR 0003)
        value = intensities[self.region]
        mode = self.force or (HIGH if value > self.threshold else LOW)
        if mode != self.mode:
            why = (f"FORCE_MODE={self.force}" if self.force else
                   f"intensity {value:.0f} {'>' if mode == HIGH else '<='} {self.threshold:.0f} in {self.region}")
            decisions.append({"action": "pause" if mode == HIGH else "resume", "region": self.region,
                              "carbon_intensity": value, "reason": why})

        # ---- message: on a change, or when the intensity moved enough
        changed = mode != self.mode or (self.last_sent and self.last_sent["region"] != self.region)
        moved = (self.last_sent is not None and self.last_sent["carbon_intensity"] > 0 and
                 abs(value - self.last_sent["carbon_intensity"]) / self.last_sent["carbon_intensity"] > self.resend)
        self.mode = mode
        if self.last_sent is None or changed or moved:
            msg = {"region": self.region, "carbon_intensity": value, "mode": mode,
                   "sent_at": datetime.now(timezone.utc).isoformat()}
            SIGNAL_SCHEMA.validate(msg)
            self.last_sent = msg
            return msg, decisions
        return None, decisions


def make_source():
    return CsvReplay(CARBON_CSV, REGIONS) if CARBON_CSV else Simulated(REGIONS)


def encode(message):
    return json.dumps(message, separators=(",", ":")).encode()


# ================================================================ 2. KAFKA, DATABASE, METRICS, START

class CarbonDecisions:
    """Table carbon_decisions (db/init/07_carbon_decisions.sql), INSERT only (ADR 0007)."""

    def __init__(self, url):
        import psycopg
        self.conn = psycopg.connect(url, autocommit=True)

    def insert(self, d, at):
        self.conn.execute("INSERT INTO carbon_decisions (at, action, region, carbon_intensity, reason) "
                          "VALUES (%s, %s, %s, %s, %s)",
                          (at, d["action"], d["region"], d["carbon_intensity"], d["reason"]))


def run(producer, source, scheduler, clock, db, stop, metrics=None, sleep=time.sleep):
    while not stop():
        now = clock.now()
        values = source.read(now)
        msg, decisions = scheduler.step(values, now)
        if metrics:
            for r, v in values.items():
                metrics["intensity"].labels(r).set(v)
            metrics["high"].set(scheduler.mode == HIGH)
        for d in decisions:
            log.info("%s %s: %s", now.strftime("%H:%M"), d["action"], d["reason"])
            if metrics:
                metrics["decisions"].labels(d["action"]).inc()
            if db:
                try:
                    db.insert(d, datetime.now(timezone.utc))
                except Exception:  # noqa: BLE001  the signal is more important than the log row
                    log.exception("carbon_decisions insert")
        if msg:
            producer.produce(TOPIC, key=msg["region"], value=encode(msg))
            producer.flush(5)
            log.info("%s sent %s %s %.0f g/kWh   (%s)", now.strftime("%H:%M"), msg["mode"], msg["region"],
                     msg["carbon_intensity"], ", ".join(f"{r} {v:.0f}" for r, v in values.items()))
        sleep(STEP_S)
    producer.flush(10)


def main():
    from confluent_kafka import Producer
    from prometheus_client import Counter, Gauge, start_http_server
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    start_http_server(METRICS_PORT)
    metrics = {"intensity": Gauge("carbon_intensity", "simulated gCO2/kWh", ["region"]),
               "high": Gauge("carbon_high_mode", "1 while the mode is high_carbon"),
               "decisions": Counter("carbon_decisions_total", "pause / resume / move", ["action"])}
    clock = SimClock(START_TIME, SPEED)
    db = None
    if USE_DB:
        try:
            db = CarbonDecisions(DATABASE_URL)
        except Exception:  # noqa: BLE001
            log.exception("no database, carbon_decisions is not written")
    stopping = []
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: stopping.append(1))
    log.info("carbon-scheduler: regions %s, threshold %.0f g/kWh, %s, simulated time %s x%g%s",
             ",".join(REGIONS), HIGH_CARBON_THRESHOLD, f"CSV {CARBON_CSV}" if CARBON_CSV else "daily curve",
             clock.now().strftime("%H:%M"), SPEED, f", FORCE_MODE={FORCE_MODE}" if FORCE_MODE else "")
    producer = Producer({"bootstrap.servers": KAFKA, "enable.idempotence": True})
    try:
        run(producer, make_source(), Scheduler(), clock, db, lambda: bool(stopping), metrics)
    except Exception:  # noqa: BLE001
        log.exception("carbon-scheduler crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
