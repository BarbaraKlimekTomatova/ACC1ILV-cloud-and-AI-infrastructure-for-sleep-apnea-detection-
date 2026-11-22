# device-simulator

UC1 (send night data). Owner: Aliénor.

Plays the home devices of the patients. Reads `kafka/messages/raw-signals/<night_id>.jsonl`
(made by [`data/03_to_kafka_messages.py`](../../data/03_to_kafka_messages.py)) and sends
**one `raw-signals` message per minute of night**, key = `patient_id`.
Every message is checked against the JSON schema before it is sent (ADR 0026).

## Modes

| Mode | Command | What happens |
|---|---|---|
| normal | `python services/device-simulator/main.py` | the 5 demo nights side by side (minute 0 of every night, then minute 1, ...), like patients sleeping at the same time |
| speed | `--speed 1` / `--speed 60` / `--speed 600` | one night-minute takes `60 / speed` seconds: 1 = real time (~7 h a night), 60 = one minute per second (~7 min), 600 = ~40 s |
| burst | `--burst` (= `--speed 0`) | everything at once, no waiting: fills `raw-signals` to test scaling (ADR 0001) |
| copies | `--burst --copies 4` | each night 4 times with a new `night_id` (`ucddb025`, `ucddb025-2`, ...), here 20 nights |
| dry run | `--dry-run` | prints one line per message, no Kafka |

Choose nights: `main.py ucddb025 ucddb010`, or `--all` for every file (33 nights).
Only the 5 demo nights have a patient (`P01` … `P05`) in the database; the other nights
have their PhysioNet id as `patient_id`, so the detector cannot save them in `raw_nights`.

`sent_at` is set to the real send time; `--keep-time` keeps the time from the file
(22:00 UTC + minute).

The program ends when all nights are sent (exit code 1 if a message was invalid or
not delivered). Ctrl+C stops it cleanly.

## Run locally

```
python data/03_to_kafka_messages.py --split demo
pip install -r services/device-simulator/requirements.txt
docker compose up -d                                   # Kafka + the 5 topics
python services/device-simulator/main.py --speed 600
```

## Settings

Command line first; each option also has an environment variable (for Docker / Kubernetes).

| Option | Variable | Default |
|---|---|---|
| night ids | `NIGHTS` (`a,b,c`) | the 5 demo nights |
| `--all` | `ALL_NIGHTS=1` | off |
| `--speed` | `SPEED` | `60` |
| `--burst` | `BURST=1` | off |
| `--copies` | `COPIES` | `1` |
| `--keep-time` | `KEEP_TIME=1` | off |
| – | `KAFKA_BOOTSTRAP` | `localhost:9092` (`kafka:29092` inside Docker) |
| – | `TOPIC` | `raw-signals` |
| – | `MESSAGES_DIR` | `kafka/messages/raw-signals` |
| – | `SCHEMA_DIR` | `kafka/schemas` |

## Tests

`pytest services/device-simulator/tests` (no Kafka needed).
