# Home Sleep Apnea Screening – a carbon-aware AI system on Kubernetes

Course project for **ACC1ILV – Cloud and AI Infrastructure**
Team: Barbara Klimek Tomatova, Aliénor Franck de Préaumont

🧭 Decisions: [ADR/](ADR/README.md)

## 🌱 Key idea: carbon-aware screening

The night analysis is **not urgent**: the result only has to be ready for the doctor by **08:00** in the morning. So the system does not have to run it as soon as the data arrives. It can **wait for electricity with lower CO₂** (the nights wait safely in Kafka), and it can **switch between a fast and an accurate model** depending on the carbon intensity and the time left until 08:00.

**Urgent alerts are the exception:** when the oxygen level (SpO₂) drops below 80 %, the alert **always runs immediately** and reaches the doctor within 5 seconds, in every carbon mode. See [ADR 0002](ADR/0002-separate-alert-path-that-never-waits.md) and [ADR 0003](ADR/0003-carbon-aware-strategy.md).

---

## What the project is about

**Situation.** People who might have sleep apnea often wait months for a night in a sleep lab. Instead, they could take a small device home that measures their oxygen level (SpO₂) and breathing during the night. In our project five demo patients (P01–P05) send real night recordings from the open PhysioNet UCDDB dataset, played back by a simulator.

**System.** The device data goes through Kafka to an AI service that finds apnea events. Then we calculate the AHI (apnea-hypopnea index, events per hour) and sort the patient into *normal, mild, moderate* or *severe*. The doctor sees the results on a dashboard and approves each one. If the oxygen level drops too low, the doctor gets an alert right away.

**Why we chose this topic.** It is a real medical problem and easy to explain. Its time constraints make it a good example for a carbon-aware system (see *Key idea* above).

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
- **Measured footprint:** the CO₂ of every training is measured with CodeCarbon, the CO₂ of every analysed night is estimated from its CPU time, the CPU power and the carbon intensity of the region (only the energy inside the containers).

---

## Architecture

The flow of one night: `device-simulator` → **raw-signals** → `apnea-detector` → **apnea-events** → `ahi-triage` → **night-results** → `doctor-dashboard`.

### Microservices

| Microservice | Use cases | What it does | Its data | Owner |
| --- | --- | --- | --- | --- |
| `device-simulator` | UC1 | Simulates the home device: replays the 5 demo nights (SpO₂ and breathing), one `raw-signals` message per minute. A burst mode sends many nights at once (to test scaling). | – (PhysioNet nights, `kafka/messages/`) | Aliénor |
| `apnea-detector` | UC2, UC5 | Saves the raw night, finds apnea events with the fast or the accurate model (chosen by the carbon mode) and estimates the CO₂ of each night. Pauses while the carbon intensity is high. Scales from 1 to 3 pods. | PostgreSQL: `raw_nights` | Barbara |
| `alert-check` (part of the detector) | UC3 | Reads the same raw data with its own consumer group that is never paused. If SpO₂ < 80 %, it sends a message to the `alerts` topic. | – | Barbara |
| `ahi-triage` | UC2 | Counts the events of a night, calculates the AHI and severity, saves the result and sends `night-results`. | PostgreSQL: `results` | Barbara |
| `alert-service` | UC3 | Reads the `alerts` topic and shows the alert to the doctor right away. | PostgreSQL: `alerts` | Aliénor |
| `doctor-dashboard` | UC3, UC4 | Patients sorted by severity, SpO₂ chart, AHI trend over several nights and alerts. The doctor approves or corrects each result; every decision is logged. | PostgreSQL: `decisions` (audit log) | Aliénor |
| `carbon-scheduler` | UC5 | Reads the simulated carbon intensity of three regions (AT / NO / PL) and sends the carbon mode to the `carbon-signal` topic. Lowers the max number of detector pods when carbon is high and moves the detector to the cleanest region. | – | Aliénor |
| `model-trainer` (Kubernetes Job) | UC7 | Trains a new version of the AI model only in a low-carbon window, measures F1 and CO₂. The new version is used only if F1 is above our threshold. | PostgreSQL: `model_versions` | Barbara |

### Other components

| Component | Why we need it |
| --- | --- |
| **Kafka** | A buffer for time-shifting: nights wait safely until the electricity is cleaner, and alerts use their own consumer group so they never wait. Topics: `raw-signals`, `apnea-events`, `night-results`, `alerts`, `carbon-signal`. See [ADR 0001](ADR/0001-kafka-as-a-buffer-for-time-shifting.md). |
| **PostgreSQL** | One database with 7 tables; each table is written by only one service ([ADR 0007](ADR/0007-one-postgresql-database-with-table-ownership.md), [doc/database-tables.md](doc/database-tables.md)). |
| **Kubernetes** | kind locally, GKE on Google Cloud ([possible GCP architecture](doc/gcp-architecture.md)). Nodes labelled AT / NO / PL (simulated regions), HPA for the detector. |
| **Prometheus + Grafana** | System health (latency, Kafka lag, pods) and AI behaviour (model, confidence, drift, CO₂). |
| **GitHub Actions** | Tests, builds and deploys the services; checks the F1 score of a new model before it is used. |

Compared to checkpoint 1 we removed **ZeroMQ** (alerts now go through Kafka) and **etcd** (the carbon mode is a Kafka topic), so every technology we keep has a clear reason.

### Technology choices

Small choices that are not architectural decisions: kind for local Kubernetes, real open data from PhysioNet (UCDDB for training and the demo, Apnea-ECG for the held-out test, see [data/DATA.md](data/DATA.md)), JSON messages checked against a JSON Schema, scikit-learn for the model, CodeCarbon for the CO₂ of training, Streamlit for the doctor dashboard.

---

## Diagrams

After the checkpoint 1 feedback we are redrawing all diagrams in **PlantUML** with UML notation:

- use case diagram (actors and use cases) – [`diagrams/usecases/`](diagrams/usecases/10.11_B_use-cases_v1.md)
- database schema (ER diagram) – `diagrams/db_schema/`, described in [doc/database-tables.md](doc/database-tables.md)
- one sequence diagram for each use case, with its description – [`diagrams/sequences/`](diagrams/sequences/)
- component diagram with interfaces
- deployment diagram (Kubernetes, regions, CI/CD)

---

## Architecture decisions

The 7 decisions that shape our architecture are in [ADR/](ADR/README.md).

---

## Repository structure

```
ADR/                 architecture decision records
diagrams/usecases/   use case diagram (PlantUML)
diagrams/sequences/  one file per use case: description + sequence diagram (PlantUML)
diagrams/db_schema/  database schema (PlantUML)
db/init/             PostgreSQL tables and users (SQL)
kafka/               Kafka messages: schemas/ (rules), examples/ (one sample each), messages/ (generated, not committed)
doc/                 database tables, possible GCP architecture
data/                data pipeline: 01_download.py, 02_clean.py, 03_to_kafka_messages.py; raw/ and clean/ nights (small .npz, in git)
services/<service>/  one folder per service: <service>.py, Dockerfile, requirements.txt, README.md
services/common/     features.py, shared by the detector and the model-trainer
tests/<service>/     unit tests (pytest, settings in pytest.ini)
models/              trained models (*.joblib, made by model-trainer, not committed)
.github/workflows/   CI, one workflow per service
k8s/                 Kubernetes manifests, one file per service (see k8s/README.md)
monitoring/          Prometheus and Grafana (to do)
notebooks/           pipeline_walkthrough.ipynb: one real night through all services, without Kafka or Docker
```

## Work split and status

✅ done · 🟡 still to do. In the order we build it: design → data → model → services → containers and CI/CD → Kubernetes → monitoring and carbon → demo.

**Status on 22 Nov 2026: 32 done, 29 to do.** Done so far: the design (use cases, ADRs, UML), the data pipeline and
database, both AI models with the F1 gate, the services device-simulator, apnea-detector and ahi-triage, CI for all
of them, and the Kubernetes manifests of Barbara's services (tested on kind: one real night went through the whole
flow). Next: the K8s base (Kafka, PostgreSQL), alert-service, carbon-scheduler, dashboard, monitoring and the demo.

### 1. Design

| Task | Owner | Status |
| --- | --- | --- |
| Use cases, non-functional requirements | both | ✅ |
| 7 ADRs ([ADR/](ADR/README.md)) | both | ✅ |
| Use case diagram | both | ✅ |
| Database schema (ER diagram) + [doc/database-tables.md](doc/database-tables.md) | both | ✅ |
| Sequence diagrams UC2, UC7 | Barbara | ✅ |
| Sequence diagrams UC1, UC3, UC4 | Aliénor | ✅ |
| Sequence diagram UC5 | Aliénor | 🟡 |
| Sequence diagram UC6 | both | 🟡 |
| Class diagrams of apnea-detector, ahi-triage, model-trainer | Barbara | 🟡 |
| Common class diagram (`class-common`) | both | 🟡 |
| Component diagram with interfaces | both | 🟡 |
| Deployment diagram (Kubernetes, regions, CI/CD) | Aliénor | 🟡 |

### 2. Data, database and Kafka

| Task | Owner | Status |
| --- | --- | --- |
| Data pipeline `data/01_download.py`, `02_clean.py` ([DATA.md](data/DATA.md)) | Barbara | ✅ |
| Tables `raw_nights`, `results`, `model_versions` | Barbara | ✅ |
| Tables `patients`, `alerts`, `decisions`, `carbon_decisions`, DB users, demo patients | Aliénor | ✅ |
| Kafka topics and JSON schemas ([kafka/](kafka/README.md)) | both | ✅ |
| Message builders `apnea-events`, `night-results` | Barbara | ✅ |
| Message builders `raw-signals`, `alerts`, `carbon-signal` | Aliénor | ✅ |
| Tests of all message builders (`tests/data`) | Aliénor | ✅ |
| `docker-compose.yml` (PostgreSQL, Kafka, topics) | Aliénor | ✅ |
| Notebook `pipeline_walkthrough.ipynb`: one night through all services | Aliénor | ✅ |

### 3. AI model

| Task | Owner | Status |
| --- | --- | --- |
| Shared per-minute features `services/common/features.py` | Barbara | ✅ |
| Accurate model (F1 0.906 on held-out Apnea-ECG) | Barbara | ✅ |
| Fast model as logistic regression in model-trainer (F1 0.882) | Barbara | ✅ |
| Fast model as a rule (SpO₂ drop ≥ 3 %) in `services/common/fast_model.py` | Aliénor | 🟡 |
| Model comparison script: F1, run time and gCO₂ of the accurate model, the fast model and the rule | Aliénor | 🟡 |

### 4. Services

| Task | Owner | Status |
| --- | --- | --- |
| `device-simulator` (UC1, normal / speed / burst modes) | Aliénor | ✅ |
| `apnea-detector` (UC2, UC5) | Barbara | ✅ |
| `alert-check` in the detector (UC3) | Barbara | ✅ |
| `ahi-triage` (UC2) | Barbara | ✅ |
| LLM summary for the doctor in `ahi-triage` (UC2 step 8) | Barbara | 🟡 |
| `alert-service` (UC3) | Aliénor | 🟡 |
| `carbon-scheduler` (UC5, regions AT / NO / PL) | Aliénor | 🟡 |
| `model-trainer` + F1 gate (UC7) | Barbara | ✅ |
| `carbon_wait.py`: training waits for `low_carbon` (UC7 step 2, needs carbon-scheduler) | Barbara | 🟡 |
| `doctor-dashboard` (UC3, UC4, Streamlit) | Aliénor | 🟡 |

### 5. Containers and CI/CD

| Task | Owner | Status |
| --- | --- | --- |
| Dockerfiles of apnea-detector, ahi-triage, model-trainer | Barbara | ✅ |
| Dockerfile of device-simulator | Aliénor | ✅ |
| Dockerfiles of alert-service, carbon-scheduler, doctor-dashboard | Aliénor | 🟡 |
| CI: tests of apnea-detector, ahi-triage, model-trainer | Barbara | ✅ |
| CI: F1 gate in GitHub Actions (`model-trainer.yml`) | Barbara | ✅ |
| CI: tests of device-simulator | Aliénor | ✅ |
| CI: tests of alert-service, carbon-scheduler | Aliénor | 🟡 |
| CD: build and push images to the registry, deploy | Aliénor | 🟡 |

### 6. Kubernetes

| Task | Owner | Status |
| --- | --- | --- |
| Base: Kafka (Strimzi), PostgreSQL, node labels AT / NO / PL | Aliénor | 🟡 |
| apnea-detector Deployment + HPA (1–3 pods), ahi-triage Deployment ([k8s/](k8s/README.md)) | Barbara | ✅ |
| model-trainer CronJob (Sunday 02:00) + PVC for the models, DB and LLM Secrets | Barbara | ✅ |
| Deployments of Aliénor's services | Aliénor | 🟡 |
| Carbon-aware redeployment and scaling (UC5, ADR 0004) | Aliénor | 🟡 |
| Local cluster on kind, then GKE | both | 🟡 |

### 7. Monitoring and carbon footprint

| Task | Owner | Status |
| --- | --- | --- |
| Prometheus `/metrics` in apnea-detector (8000) and ahi-triage (8001) | Barbara | ✅ |
| CO₂ per night in apnea-detector (CPU time × power × carbon intensity), CodeCarbon in model-trainer | Barbara | ✅ |
| CodeCarbon for the LLM call | Barbara | 🟡 |
| Prometheus + Grafana dashboard "System health" | Aliénor | 🟡 |
| Grafana dashboard "AI & carbon" | Barbara | 🟡 |
| Carbon-aware model switching: carbon-scheduler decides when the detector uses the fast model, Grafana shows the CO₂ saved against the F1 lost | Aliénor | 🟡 |
| UC6: drift and low-confidence warnings | both | 🟡 |

### 8. Demo and checkpoint 2 (4 Dec 2026)

| Task | Owner | Status |
| --- | --- | --- |
| Whole flow end to end in docker compose | both | 🟡 |
| Whole flow end to end in Kubernetes | both | 🟡 |
| Measured CO₂ and sustainability trade-offs for the presentation | both | 🟡 |
| 5-minute presentation | both | 🟡 |

### Who covers which grading criterion

Both of us work on every criterion. ✅ / 🟡 as in the tables above.

| Criterion (weight) | Barbara | Aliénor |
| --- | --- | --- |
| Architecture, ADRs, UML diagrams (25 %) | ADRs and use cases together ✅, sequence diagrams UC2 and UC7 ✅, ER diagram together ✅, class diagrams of her 3 services 🟡, component diagram together 🟡 | ADRs and use cases together ✅, sequence diagrams UC1, UC3, UC4 ✅, ER diagram together ✅, sequence diagram UC5 🟡, deployment diagram 🟡, component diagram together 🟡 |
| Code (15 %) | `apnea-detector` with alert-check ✅, `ahi-triage` ✅, `model-trainer` + F1 gate ✅, shared `features.py` ✅, LLM summary 🟡, `carbon_wait.py` 🟡 | message builders ✅, `device-simulator` ✅, `alert-service` 🟡, `carbon-scheduler` 🟡, `doctor-dashboard` 🟡 |
| Data handling (10 %) | data pipeline (download, clean, splits) ✅, tables `raw_nights`, `results`, `model_versions` ✅, topics `apnea-events`, `night-results` ✅ | tables `patients`, `alerts`, `decisions`, `carbon_decisions` and DB users ✅, topics `raw-signals`, `alerts`, `carbon-signal` ✅, `docker-compose.yml` ✅, pipeline walkthrough notebook ✅ |
| AI model (10 %) | features ✅, accurate model (F1 0.906) ✅, fast model as logistic regression (F1 0.882) ✅, retraining (UC7) ✅, LLM summary 🟡 | fast model as a rule 🟡, model comparison script 🟡 |
| Carbon footprint (10 %) | CO₂ per night in apnea-detector ✅, CodeCarbon in model-trainer ✅, CodeCarbon for the LLM call 🟡, training only in a low-carbon window 🟡 | carbon-scheduler with regions AT / NO / PL 🟡, carbon-aware model switching 🟡, `carbon_decisions` table ✅ |
| Deployment, Docker and Kubernetes (10 %) | Dockerfiles of her 3 services ✅, detector Deployment + HPA, triage Deployment, trainer CronJob, Secrets ✅ (tested on kind) | `docker-compose.yml` ✅, Dockerfile of device-simulator ✅, Dockerfiles of her other services 🟡, K8s base (Kafka, PostgreSQL, node labels) 🟡, carbon-aware redeployment 🟡 |
| Monitoring, Prometheus and Grafana (10 %) | `/metrics` in apnea-detector and ahi-triage ✅, Grafana "AI & carbon" 🟡, UC6 warnings together 🟡 | Prometheus + Grafana "System health" 🟡, Grafana CO₂ saved vs F1 lost 🟡, UC6 warnings together 🟡 |
| CI/CD (5 %) | CI tests of her 3 services ✅, F1 gate in GitHub Actions ✅ | CI tests of device-simulator ✅, CI tests of her other services 🟡, CD: build, push and deploy 🟡 |
| Sustainability trade-offs (5 %) | carbon-aware analysis in the detector: accurate, pause or fast before 08:00 (ADR 0003) ✅, accurate vs fast model F1 ✅ | model comparison F1 / run time / gCO₂ 🟡, CO₂ saved vs F1 lost in Grafana 🟡, redeployment to a cleaner region (ADR 0004) 🟡 |
