# Kafka messages

Everything about the messages our services send each other through Kafka. The database tables are in [`db/init/`](../db/init/) and described in [`doc/database-tables.md`](../doc/database-tables.md).

| Folder | What is inside | Committed |
|---|---|---|
| [`schemas/`](schemas/) | JSON Schema of each message: the rules (fields, types, allowed values) | yes |
| [`examples/`](examples/) | one hand-written sample message per schema, valid against it | yes |
| `messages/<topic>/` | real messages built from the PhysioNet nights by [`data/03_to_kafka_messages.py`](../data/03_to_kafka_messages.py): `<night_id>.jsonl`, one line = one message | no (generated) |

## Naming

- **Topics:** lowercase kebab-case nouns in plural, e.g. `night-results`. One topic = one kind of message.
- **Schemas:** named after the Schema Registry subject (TopicNameStrategy): `<topic>-value.schema.json` for the message value. The key is always `patient_id` (a string), so there are no `-key` schemas.
- **Examples:** same name as the schema: `<topic>-value.example.json`.
- **Real messages:** one folder per topic, one file per night: `messages/<topic>/<night_id>.jsonl` (JSON Lines).

## Topics

| # | Topic | From → to | Value schema |
|---|---|---|---|
| 1 | `raw-signals` | device-simulator → apnea-detector, alert-check | – (to do) |
| 2 | `alerts` | alert-check → alert-service | – (to do) |
| 3 | `apnea-events` | apnea-detector → ahi-triage | [apnea-events-value.schema.json](schemas/apnea-events-value.schema.json) |
| 4 | `night-results` | ahi-triage → doctor-dashboard | [night-results-value.schema.json](schemas/night-results-value.schema.json) |
| 5 | `carbon-signal` | carbon-scheduler → apnea-detector | – (to do) |

`night-results` carries almost the same values as the `results` table: ahi-triage saves the row and sends the message at the same time.
