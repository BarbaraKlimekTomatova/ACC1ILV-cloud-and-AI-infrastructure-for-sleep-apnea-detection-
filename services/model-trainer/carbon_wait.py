"""Wait for a low-carbon window before training (UC7 step 2, alternative flow A2, ADR 0005).

    python services/model-trainer/train.py --wait-low-carbon            # waits, then trains
    WAIT_LOW_CARBON=1 MAX_WAIT_S=21600 python services/model-trainer/train.py

How it works
  * The carbon-scheduler sends the carbon mode to the Kafka topic `carbon-signal`
    (kafka/schemas/carbon-signal-value.schema.json) when it changes:
        {"region": "NO", "carbon_intensity": 35.0, "mode": "low_carbon", "sent_at": "..."}
    So the newest message of the topic is the mode right now.
  * The trainer starts at that newest message. `low_carbon` -> train now (in that region).
    `high_carbon` or an empty topic -> keep listening until a `low_carbon` message arrives.
  * If no low-carbon window comes within MAX_WAIT_S (A2), the trainer stops WITHOUT training
    and without a model_versions row; the next CronJob run tries again.

The trainer needs only the message format, not the carbon-scheduler itself: for a test,
send a message by hand (see services/model-trainer/README.md).
"""

import json
import logging
import os
import time
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
TOPIC = "carbon-signal"
DEFAULT_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")   # kafka:29092 inside Docker
DEFAULT_MAX_WAIT_S = float(os.environ.get("MAX_WAIT_S", 6 * 3600))      # CronJob 02:00 -> give up at 08:00
SCHEMA_DIR = Path(os.environ.get("SCHEMA_DIR", str(ROOT / "kafka" / "schemas")))
SCHEMA = Draft202012Validator(json.loads((SCHEMA_DIR / "carbon-signal-value.schema.json").read_text()))

log = logging.getLogger("carbon-wait")


class NoLowCarbonWindow(Exception):
    """No low_carbon message arrived before the deadline (UC7 A2)."""


def is_low_carbon(signal):
    """True if a carbon-signal message says we may train now."""
    return signal.get("mode") == "low_carbon"


def parse(value):
    """Kafka value -> carbon-signal dict, or None if it is not valid (it is ignored)."""
    try:
        signal = json.loads(value)
        SCHEMA.validate(signal)
        return signal
    except Exception as e:  # noqa: BLE001  a bad message must not stop the training
        log.warning("ignored a bad carbon-signal message: %s", str(e)[:200])
        return None


def start_at_newest(consumer, topic=TOPIC, timeout=10.0):
    """Assign every partition of the topic at its NEWEST message (or its start if it is empty),
    so the first message we read is the mode right now and then every new one."""
    from confluent_kafka import TopicPartition
    partitions = consumer.list_topics(topic, timeout=timeout).topics[topic].partitions
    assignment = []
    for p in partitions:
        low, high = consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=timeout)
        assignment.append(TopicPartition(topic, p, max(high - 1, low)))
    consumer.assign(assignment)


def wait_for_low_carbon(bootstrap=DEFAULT_BOOTSTRAP, timeout_s=DEFAULT_MAX_WAIT_S, poll_s=5.0,
                        consumer=None, clock=time.monotonic):
    """Block until the carbon mode is low_carbon; return that carbon-signal message.

    Raises NoLowCarbonWindow after `timeout_s` seconds. `consumer` and `clock` are for the tests.
    """
    own = consumer is None
    if own:
        from confluent_kafka import Consumer
        consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": "model-trainer",
                             "enable.auto.commit": False, "auto.offset.reset": "latest"})
    deadline = clock() + timeout_s
    try:
        start_at_newest(consumer)
        mode = None
        while clock() < deadline:
            msg = consumer.poll(poll_s)
            if msg is None or msg.error():
                continue
            signal = parse(msg.value())
            if signal is None:
                continue
            if signal["mode"] != mode:
                mode = signal["mode"]
                log.info("%s in %s (%.0f gCO2/kWh)%s", mode, signal["region"], signal["carbon_intensity"],
                         "" if is_low_carbon(signal) else ", waiting ...")
            if is_low_carbon(signal):
                return signal
        raise NoLowCarbonWindow(f"no low_carbon within {timeout_s:.0f} s")
    finally:
        if own:
            consumer.close()
