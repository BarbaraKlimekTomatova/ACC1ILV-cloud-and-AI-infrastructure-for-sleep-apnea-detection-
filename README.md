# Home Sleep Apnea Screening – a carbon-aware AI system on Kubernetes

Course project for **ACC1ILV – Cloud and AI Infrastructure**
Team: Barbara Klimek Tomatova, Aliénor Franck de Préaumont

📄 Project summary: [doc/Klimek_Préaumont_Project_summary.pdf](doc/Klimek_Préaumont_Project_summary.pdf) · 🧭 Decisions: [ADR/](ADR/README.md)

---

## What the project is about

**Situation.** People who might have sleep apnea often wait months for a night in a sleep lab. Instead, they could take a small device home that measures their oxygen level (SpO₂) and breathing during the night. In our project we simulate five patients with several nights each.

**System.** The device data goes through Kafka to an AI service that finds apnea events. Then we calculate the AHI (apnea-hypopnea index, events per hour) and sort the patient into *normal, mild, moderate* or *severe*. The doctor sees the results on a dashboard and approves each one. If the oxygen level drops too low, the doctor gets an alert right away.

**Why we chose this topic.** It is a real medical problem and easy to explain. The night analysis is not urgent, it only has to be ready by 08:00 in the morning. So the system can wait for electricity with lower CO₂ and choose between a fast and an accurate model. Alerts are the exception and always run immediately.

**Out of scope:** login for patients and doctors, sending reports to patients, therapy monitoring.

---

## Use cases

The actors are outside our system: the home device, the doctor, the external carbon intensity source and our team as operators. The carbon scheduler and Kubernetes are parts of the system, so they are not actors.

| # | Use case | Actor | Description |
| --- | --- | --- | --- |
| UC1 | Upload night recording | Home device (simulated) | The device sends the SpO₂ and breathing data of a night minute by minute. Each patient sends several nights. The raw night is saved. |
| UC2 | Screen night | Carbon intensity source (secondary) | The system finds apnea events, calculates the AHI and severity and saves the result. The carbon mode decides when the analysis runs (before 08:00) and if the fast or the accurate model is used. The CO₂ of each analysis is measured. |
| UC3 | Raise urgent alert – `<<extend>>` UC2 | Doctor | Only when SpO₂ goes below 80 %: the doctor gets an alert right away. Alerts never wait for low-carbon electricity. |
| UC4 | Review & approve result | Doctor | The doctor sees the patients sorted by severity, opens a report with the SpO₂ chart and the AHI trend over the patient's previous nights, and approves or corrects the result. Every decision is logged. |
| UC5 | Adapt to carbon intensity | Carbon intensity source | When the (simulated) carbon intensity changes, the system changes its behaviour: it delays the analysis, switches between the fast and the accurate model, lowers the maximum number of detector pods and moves the detector to a node in a cleaner (simulated) region (AT / NO / PL). |
| UC6 | Monitor system & footprint | Operator / Team | The team sees the system health (latency, Kafka lag, pods) and the AI behaviour (model used, confidence, events per hour, CO₂ per night). It gets a warning when the model drifts or its confidence drops. |
| UC7 | Retrain model | Operator / Team, Carbon intensity source | The team starts a new training of the AI model. The training runs only in a low-carbon window, the new model version is used only if its F1 score is above our threshold. |

**Non-functional requirements**

- **Scalability:** when many nights arrive at the same time, Kubernetes scales the apnea-detector from 1 to 3 pods and back (this was UC6 "Scale under load" before; it is a quality requirement, not a use case).
- **Alert latency:** an urgent alert reaches the doctor within 5 seconds, in every carbon mode.
- **Deadline:** every night is analysed before 08:00.
- **No data loss:** a night is not lost when a service or one Kafka broker stops.
- **Measured footprint:** the CO₂ of every analysis and training is measured with CodeCarbon (only the energy inside the containers).

---

## Architecture

The flow of one night: `device-simulator` → **raw-signals** → `apnea-detector` → **apnea-events** → `ahi-triage` → **night-results** → `doctor-dashboard`.

### Microservices

| Microservice | Use cases | What it does | Its data | Owner |
| --- | --- | --- | --- | --- |
| `device-simulator` | UC1 | Simulates the home device: sends several nights of SpO₂ and breathing data for 5 patients, one message per minute. A burst mode sends many nights at once (to test scaling). | – (synthetic data) | Aliénor |
| `apnea-detector` | UC2, UC5 | Saves the raw night, finds apnea events with the fast or the accurate model (chosen by the carbon mode) and measures the CO₂ with CodeCarbon. Pauses while the carbon intensity is high. Scales from 1 to 3 pods. | PostgreSQL: `raw_nights` | Barbara |
| `alert-check` (part of the detector) | UC3 | Reads the same raw data with its own consumer group that is never paused. If SpO₂ < 80 %, it sends a message to the `alerts` topic. | – | Barbara |
| `ahi-triage` | UC2 | Counts the events of a night, calculates the AHI and severity, saves the result and sends `night-results`. | PostgreSQL: `results` | Aliénor |
| `alert-service` | UC3 | Reads the `alerts` topic and shows the alert to the doctor right away. | PostgreSQL: `alerts` | Barbara |
| `doctor-dashboard` | UC3, UC4 | Patients sorted by severity, SpO₂ chart, AHI trend over several nights and alerts. The doctor approves or corrects each result; every decision is logged. | PostgreSQL: `decisions` (audit log) | Aliénor |
| `carbon-scheduler` | UC5 | Reads the simulated carbon intensity of three regions (AT / NO / PL) and sends the carbon mode to the `carbon-signal` topic. Lowers the max number of detector pods when carbon is high and moves the detector to the cleanest region. | – | Barbara |
| `model-trainer` (Kubernetes Job) | UC7 | Trains a new version of the AI model only in a low-carbon window, measures F1 and CO₂. The new version is used only if F1 is above our threshold. | model versions | Barbara |

### Other components

| Component | Why we need it |
| --- | --- |
| **Kafka** | A buffer for time-shifting: nights wait safely until the electricity is cleaner, and alerts use their own consumer group so they never wait. Topics: `raw-signals`, `apnea-events`, `night-results`, `alerts`, `carbon-signal`. See [ADR 0001](ADR/0001-kafka-as-a-buffer-for-time-shifting.md). |
| **PostgreSQL** | One database with 5 tables; each table is written by only one service. |
| **Kubernetes** | kind locally, GKE on Google Cloud. Nodes labelled AT / NO / PL (simulated regions), HPA for the detector. |
| **Prometheus + Grafana** | System health (latency, Kafka lag, pods) and AI behaviour (model, confidence, drift, CO₂). |
| **GitHub Actions** | Tests, builds and deploys the services; checks the F1 score of a new model before it is used. |

Compared to checkpoint 1 we removed **ZeroMQ** (alerts now go through Kafka) and **etcd** (the carbon mode is a Kafka topic), so every technology we keep has a clear reason.

### Technology choices

Small choices that are not architectural decisions: kind for local Kubernetes, synthetic data instead of PhysioNet (PhysioNet stays optional), JSON messages with a fixed schema, scikit-learn for the model, CodeCarbon for measuring CO₂.

---

## Diagrams

After the checkpoint 1 feedback we are redrawing all diagrams in **PlantUML** with UML notation:

- use case diagram – `diagrams/usecases/`
- one sequence diagram for each important use case: Screen night (UC2), Raise urgent alert (UC3), Adapt to carbon intensity (UC5)
- component diagram with interfaces
- deployment diagram (Kubernetes, regions, CI/CD)

The old Mermaid diagrams from checkpoint 1 are in `diagrams/archive/`.

---

## Architecture decisions

The 7 decisions that shape our architecture are in [ADR/](ADR/README.md). Our first 28 ADRs are in [ADR/Archive/](ADR/Archive/README.md).

---

## Repository structure

```
ADR/                 architecture decision records (Archive/ = before the feedback)
diagrams/usecases/   use case diagrams (PlantUML)
diagrams/archive/    old Mermaid diagrams from checkpoint 1
doc/                 project summary from checkpoint 1 (PDF)
```

## Status

Reworking the design after the checkpoint 1 feedback: use cases and ADRs are updated, PlantUML diagrams are in progress. Next: sequence diagrams, then deployment to Kubernetes.
