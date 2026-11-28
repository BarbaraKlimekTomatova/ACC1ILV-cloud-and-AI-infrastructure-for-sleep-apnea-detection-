# Sequence diagrams

One sequence diagram per scenario, in PlantUML. Every diagram has its own description (`.md`):
actors, trigger, main flow with the step numbers of the diagram, alternative flows and the postcondition.

| Use cases | Scenario | Description | Diagram | Author |
| --- | --- | --- | --- | --- |
| UC1, UC2, UC3 | Process one night: upload, screen, urgent alert (UC3 `<<extend>>` UC2) | [AB_UC1-UC3_process-one-night.md](AB_UC1-UC3_process-one-night.md) | [png](AB_UC1-UC3_process-one-night.png) · [puml](AB_UC1-UC3_process-one-night.puml) | Aliénor, Barbara |
| UC4 | Review and approve a result | [A_UC4-review-a-result.md](A_UC4-review-a-result.md) | [png](A_UC4-review-a-result.png) · [puml](A_UC4-review-a-result.puml) | Aliénor |
| UC5 | Adapt to carbon intensity | [A_UC5-adapt-to-carbon.md](A_UC5-adapt-to-carbon.md) | [png](A_UC5-adapt-to-carbon.png) · [puml](A_UC5-adapt-to-carbon.puml) | Aliénor |
| UC6 | Monitor system and footprint | [B_UC6-monitor-system-and-footprint.md](B_UC6-monitor-system-and-footprint.md) | [png](B_UC6-monitor-system-and-footprint.png) · [puml](B_UC6-monitor-system-and-footprint.puml) | Barbara |
| UC7 | Retrain model | [B_UC7-retrain-model.md](B_UC7-retrain-model.md) | [png](B_UC7-retrain-model.png) · [puml](B_UC7-retrain-model.puml) | Barbara |

UC1–UC3 are in one diagram because they handle the same `raw-signals` minutes at the same time:
a `par` fragment shows the three consumer groups side by side, and every part is labelled with its use case.

## Notation

| Arrow | PlantUML | Meaning |
| --- | --- | --- |
| solid line, open arrowhead | `->>` | asynchronous message: a Kafka topic, the sender does not wait |
| solid line, filled arrowhead | `->` | synchronous call: SQL, HTTP, Kubernetes API, the caller waits |
| dashed line | `-->` | reply to a synchronous call |
| arrow back to the same lifeline | `A -> A` | internal processing of a service |

- Every message has a number (`autonumber`); the descriptions refer to these numbers.
- The bar on a lifeline (`activate` / `deactivate`) shows when a participant is working.
- Fragments: `loop` repeats, `alt` = alternatives, `opt` = only if, `par` = at the same time.
- Kafka topics are drawn as queues (yellow), PostgreSQL as a database.

## File names

`<author>_<use cases>_<short-name>` with `.puml` (source), `.png` (image) and `.md` (description).
Author: `A` = Aliénor, `B` = Barbara, `AB` = both. Git keeps the history, so there is no date and no version in the name.

Render after a change (the UC1–UC3 diagram is larger than PlantUML's default limit of 4096 px):

```
PLANTUML_LIMIT_SIZE=16384 plantuml -tpng diagrams/sequences/*.puml
```
