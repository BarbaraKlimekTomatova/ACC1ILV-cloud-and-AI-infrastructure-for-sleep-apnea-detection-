"""device-simulator (UC1). Owner: Aliénor.

    python services/device-simulator/main.py                    # 5 demo nights, speed 60
    python services/device-simulator/main.py --speed 1          # real time (one night = ~7 h)
    python services/device-simulator/main.py --burst --copies 4 # 20 nights at once, no waiting
    python services/device-simulator/main.py --dry-run          # print, no Kafka

Plays the home devices: reads kafka/messages/raw-signals/<night_id>.jsonl
(made by data/03_to_kafka_messages.py) and sends one raw-signals message per
minute of night to Kafka, key = patient_id.

Two modes:
  normal  the nights run side by side, like patients sleeping at the same time:
          minute 0 of every night, then minute 1, ... One night-minute takes
          60 / SPEED seconds (SPEED 1 = real time, 60 = one minute per second).
  burst   every minute of every night as fast as Kafka takes them (no waiting),
          to fill raw-signals and test scaling (ADR 0001). --copies N sends each
          night N times with a new night_id (ucddb025, ucddb025-2, ...).

The file has two halves:
  1. the logic (which nights, order, timing, message changes): no Kafka, so the tests run without it
  2. Kafka and the start

Each message is checked against kafka/schemas/raw-signals-value.schema.json before it is sent (ADR 0026).
Settings: command line or environment variables, see README.md.
"""

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- settings
env = os.environ.get
KAFKA = env("KAFKA_BOOTSTRAP", "localhost:9092")                     # kafka:29092 inside Docker
TOPIC = env("TOPIC", "raw-signals")
MESSAGES_DIR = Path(env("MESSAGES_DIR", str(ROOT / "kafka" / "messages" / "raw-signals")))
SCHEMA_DIR = Path(env("SCHEMA_DIR", str(ROOT / "kafka" / "schemas")))

# the 5 demo nights = demo patients P01-P05 (db/init/09_insert_demo_patients.sql)
DEMO_NIGHTS = ["ucddb018", "ucddb017", "ucddb013", "ucddb010", "ucddb025"]

log = logging.getLogger("device-simulator")
stop = threading.Event()


# ================================================================ 1. LOGIC (no Kafka)

def choose_nights(messages_dir, nights=None, all_nights=False):
    """Night ids to send: the ones asked for, all files, or the 5 demo nights."""
    available = sorted(p.stem for p in Path(messages_dir).glob("*.jsonl"))
    if all_nights:
        chosen = available
    else:
        chosen = list(nights) if nights else DEMO_NIGHTS
    missing = [n for n in chosen if n not in available]
    if missing:
        raise FileNotFoundError(
            f"no messages for {', '.join(missing)} in {messages_dir}; "
            "run first: python data/03_to_kafka_messages.py")
    if not chosen:
        raise FileNotFoundError(f"no .jsonl files in {messages_dir}")
    return chosen


def copy_id(night_id, copy):
    """Copy 1 keeps the night id, copy 2 -> ucddb025-2, ..."""
    return night_id if copy == 1 else f"{night_id}-{copy}"


def read_night(path):
    """One .jsonl file -> list of messages (one per minute), sorted by minute."""
    with open(path, encoding="utf-8") as f:
        messages = [json.loads(line) for line in f if line.strip()]
    return sorted(messages, key=lambda m: m["minute"])


def interleave(nights):
    """{night_id: [messages]} -> messages minute by minute across all nights.

    Minute 0 of every night, then minute 1, ... A short night simply ends earlier.
    Yields (step, message), step = index of the night-minute (0, 1, 2, ...).
    """
    longest = max((len(ms) for ms in nights.values()), default=0)
    for step in range(longest):
        for messages in nights.values():
            if step < len(messages):
                yield step, messages[step]


def plan(messages_dir, night_ids, copies=1):
    """Load the nights (with copies) -> {night_id: [messages]}."""
    nights = {}
    for night_id in night_ids:
        original = read_night(Path(messages_dir) / f"{night_id}.jsonl")
        for c in range(1, copies + 1):
            new_id = copy_id(night_id, c)
            nights[new_id] = [{**m, "night_id": new_id} for m in original]
    return nights


def prepare(message, keep_time=False, now=None):
    """Message ready to send: sent_at = real send time (unless keep_time)."""
    if keep_time:
        return message
    sent_at = (now or datetime.now(timezone.utc)).isoformat()
    return {**message, "sent_at": sent_at}


def wait_seconds(step, speed, started, now):
    """How long to wait before night-minute `step`. speed 0 = no waiting (burst)."""
    if not speed:
        return 0.0
    return max(0.0, started + step * 60.0 / speed - now)


def encode(message):
    return json.dumps(message, separators=(",", ":")).encode()


def load_schema(schema_dir=SCHEMA_DIR):
    path = Path(schema_dir) / "raw-signals-value.schema.json"
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def run(producer, nights, speed, keep_time=False, schema=None,
        clock=time.monotonic, sleep=time.sleep, topic=TOPIC):
    """Send the nights to Kafka. Returns {"sent": n, "invalid": n}.

    producer  anything with produce(topic, key=, value=) and poll(timeout)
    """
    schema = schema or load_schema()
    sent = invalid = 0
    started = clock()
    last_step = -1
    for step, message in interleave(nights):
        if stop.is_set():
            log.info("stopped at night-minute %s", step)
            break
        if step != last_step:
            pause = wait_seconds(step, speed, started, clock())
            if pause:
                sleep(pause)
            last_step = step
            if step % 60 == 0:
                log.info("night-minute %s, %s messages sent", step, sent)
        message = prepare(message, keep_time)
        errors = sorted(schema.iter_errors(message), key=str)
        if errors:                                   # never send a bad message (ADR 0026)
            invalid += 1
            log.error("invalid message %s minute %s: %s", message.get("night_id"),
                      message.get("minute"), errors[0].message[:200])
            continue
        send(producer, topic, message)
        sent += 1
    return {"sent": sent, "invalid": invalid}


def send(producer, topic, message):
    """produce(); if the local queue is full (burst), wait for Kafka and try again."""
    while True:
        try:
            producer.produce(topic, key=message["patient_id"], value=encode(message))
            producer.poll(0)
            return
        except BufferError:
            producer.poll(1.0)


# ================================================================ 2. KAFKA AND START

class DryRunProducer:
    """Prints one line per message instead of sending it (--dry-run)."""

    def produce(self, topic, key, value):
        m = json.loads(value)
        print(f"{topic} key={key} {m['night_id']} minute={m['minute']} "
              f"is_last={m['is_last']} spo2[0]={m['spo2'][0]}")

    def poll(self, timeout=0):
        return 0

    def flush(self, timeout=None):
        return 0


class Delivery:
    """Counts what Kafka confirmed."""

    def __init__(self):
        self.ok = self.failed = 0

    def __call__(self, err, msg):
        if err is not None:
            self.failed += 1
            log.error("delivery failed: %s", err)
        else:
            self.ok += 1


def kafka_producer(delivery):
    from confluent_kafka import Producer
    p = Producer({"bootstrap.servers": KAFKA, "linger.ms": 20, "enable.idempotence": True,
                  "compression.type": "lz4", "on_delivery": delivery})
    return p


def env_float(name, default):
    return float(env(name, default))


def parse_args(argv=None):
    a = argparse.ArgumentParser(description="Send nights to the raw-signals topic.")
    a.add_argument("nights", nargs="*", default=[n for n in env("NIGHTS", "").split(",") if n],
                   help="night ids (default: the 5 demo nights; env NIGHTS=a,b)")
    a.add_argument("--all", action="store_true", default=env("ALL_NIGHTS", "0") == "1",
                   help="every .jsonl file in MESSAGES_DIR (env ALL_NIGHTS=1)")
    a.add_argument("--speed", type=float, default=env_float("SPEED", "60"),
                   help="1 = real time, 60 = one night-minute per second, 0 = no waiting (env SPEED)")
    a.add_argument("--burst", action="store_true", default=env("BURST", "0") == "1",
                   help="send everything at once, no waiting (env BURST=1)")
    a.add_argument("--copies", type=int, default=int(env("COPIES", "1")),
                   help="send each night N times with a new night_id (env COPIES)")
    a.add_argument("--keep-time", action="store_true", default=env("KEEP_TIME", "0") == "1",
                   help="keep sent_at from the files instead of the real send time")
    a.add_argument("--dry-run", action="store_true", help="print the messages, no Kafka")
    args = a.parse_args(argv)
    if args.speed < 0:
        a.error("--speed must be >= 0")
    if args.copies < 1:
        a.error("--copies must be >= 1")
    if args.burst:
        args.speed = 0
    return args


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    night_ids = choose_nights(MESSAGES_DIR, args.nights, args.all)
    nights = plan(MESSAGES_DIR, night_ids, args.copies)
    total = sum(len(ms) for ms in nights.values())
    longest = max(len(ms) for ms in nights.values())
    mode = "burst" if args.speed == 0 else f"speed {args.speed:g}"
    duration = "as fast as possible" if args.speed == 0 else f"~{longest / args.speed:.1f} min"
    log.info("%s nights, %s messages, %s, %s -> %s (%s)", len(nights), total, mode, duration,
             TOPIC, "dry run" if args.dry_run else KAFKA)

    delivery = Delivery()
    producer = DryRunProducer() if args.dry_run else kafka_producer(delivery)
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: stop.set())

    result = run(producer, nights, args.speed, args.keep_time)
    left = producer.flush(30)
    log.info("done: %s sent, %s invalid, %s confirmed by Kafka, %s failed, %s not delivered",
             result["sent"], result["invalid"], delivery.ok, delivery.failed, left)
    failed = result["invalid"] or delivery.failed or left
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
