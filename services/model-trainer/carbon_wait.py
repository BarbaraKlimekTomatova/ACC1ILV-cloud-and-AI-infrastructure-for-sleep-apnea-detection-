"""Wait for a low-carbon window before training (UC7 step 2, alternative flow A2, ADR 0005).

SKELETON – not used by train.py yet. The TODOs below are the plan.

How it should work
  * The carbon-scheduler sends the current carbon mode to the Kafka topic
    `carbon-signal` (kafka/schemas/carbon-signal-value.schema.json):
        {"region": "NO", "carbon_intensity": 35.0, "mode": "low_carbon", "sent_at": "..."}
    It sends a message only when the mode CHANGES, so the newest message of the
    topic is the mode right now.
  * The trainer reads that newest message. `low_carbon` -> train now.
    `high_carbon` -> keep listening until a `low_carbon` message arrives.
  * If no low-carbon window comes before the deadline of the Job (A2), the
    trainer stops WITHOUT training and without a model_versions row; the next
    CronJob run tries again.

Planned use in train.py
    from carbon_wait import wait_for_low_carbon, NoLowCarbonWindow
    if a.wait_low_carbon:
        try:
            signal = wait_for_low_carbon(timeout_s=a.max_wait_s)
            a.region = signal["region"]          # store where the training ran
        except NoLowCarbonWindow:
            print("no low-carbon window, try again next run")
            return None                          # exit 0: nothing changed (A2)
"""

import os
import time

TOPIC = "carbon-signal"
DEFAULT_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")   # kafka:29092 inside Docker
DEFAULT_MAX_WAIT_S = 6 * 3600          # TODO: agree with the team (CronJob Sunday 02:00 -> give up at 08:00?)


class NoLowCarbonWindow(Exception):
    """No low_carbon message arrived before the deadline (UC7 A2)."""


def is_low_carbon(signal):
    """True if a carbon-signal message says we may train now."""
    return signal.get("mode") == "low_carbon"


def latest_signal(consumer, topic=TOPIC):
    """The newest carbon-signal message (= the mode right now), or None if the topic is empty.

    TODO:
      1. for each partition of `topic` get the high watermark
         (consumer.get_watermark_offsets) and assign the consumer to offset high - 1
      2. poll that one message, json.loads(msg.value())
      3. validate it with jsonschema against kafka/schemas/carbon-signal-value.schema.json
      4. if there are several partitions, take the message with the newest `sent_at`
    """
    raise NotImplementedError


def wait_for_low_carbon(bootstrap=DEFAULT_BOOTSTRAP, timeout_s=DEFAULT_MAX_WAIT_S, poll_s=5.0):
    """Block until the carbon mode is low_carbon; return that carbon-signal message.

    Raises NoLowCarbonWindow after `timeout_s` seconds.

    TODO:
      1. create the consumer (confluent_kafka.Consumer) with
         {"bootstrap.servers": bootstrap, "group.id": "model-trainer",
          "enable.auto.commit": False, "auto.offset.reset": "latest"}
         and add confluent-kafka + jsonschema to services/model-trainer/requirements.txt
      2. signal = latest_signal(consumer); if it is low_carbon -> return it
      3. otherwise subscribe to TOPIC and poll(poll_s) in a loop until a message
         with mode low_carbon arrives -> return it
      4. stop when time.monotonic() > deadline -> raise NoLowCarbonWindow
      5. always consumer.close() (try/finally)
      6. log every mode change: "high_carbon in AT (420 g/kWh), waiting ..."
      7. Prometheus (UC6, optional): gauge model_trainer_waiting_seconds
    """
    deadline = time.monotonic() + timeout_s
    raise NotImplementedError(f"skeleton, deadline would be in {deadline - time.monotonic():.0f} s")


# TODO in train.py
#   * new flags --wait-low-carbon (env WAIT_LOW_CARBON=1 in the Kubernetes Job)
#     and --max-wait-s; off by default so local runs and CI never wait
#   * set the region of the model_versions row from the carbon-signal message
#
# TODO tests (tests/model-trainer/test_carbon_wait.py), without a real Kafka:
#   * a fake consumer that returns prepared messages
#   * low_carbon at once -> returns immediately
#   * high_carbon then low_carbon -> returns the second message
#   * only high_carbon -> NoLowCarbonWindow after a tiny timeout_s
#   * empty topic -> keeps waiting (the carbon-scheduler has not sent anything yet)
