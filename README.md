# Home Sleep Apnea Screening – a carbon-aware AI system on Kubernetes

Course project for **ACC1ILV – Cloud and AI Infrastructure**
Team: Barbara Klimek Tomatova, Aliénor Franck de Préaumont

📄 Project summary: [doc/Klimek_Préaumont_Project_summary.pdf](doc/Klimek_Préaumont_Project_summary.pdf) · 🧭 Decisions: [ADR/](ADR/README.md)

---

## What the project is about

**Situation.** People who might have sleep apnea often wait months for a night in a sleep lab. Instead, they could take a small device home that measures their oxygen level (SpO₂) and breathing during the night. In our project we simulate five patients.

**System.** The device data goes through Kafka (3 brokers, so one can fail) to an AI service that finds apnea events. Then we calculate the AHI (apnea-hypopnea index, events per hour) and sort the patient into *normal, mild, moderate* or *severe*. The doctor sees the results on a dashboard and approves each one. If the oxygen level drops too low, the doctor gets an alert right away.

**Why we chose this topic.** It is a real medical problem and easy to explain. The night analysis is not urgent, it only has to be ready by 08:00 in the morning. So the system can wait for electricity with lower CO₂ and choose between a fast and an accurate model. Alerts are the exception and always run immediately.

**Out of scope:** login for patients and doctors, history over several nights, sending reports to patients, therapy monitoring.

---

## Use cases

| # | Use case | Actor | Description |
| --- | --- | --- | --- |
| UC1 | Send night data | Device (simulator) | The simulator sends the SpO₂ and breathing data of a night minute by minute over Kafka. The raw night is saved in the database. |
| UC2 | Analyse a night | System | The system finds apnea events with the fast or the accurate model (depending on the carbon mode), calculates the AHI and severity and saves the result. It also measures how much CO₂ the analysis used. |
| UC3 | Raise an alert | System, doctor | If SpO₂ goes below 80 %, an alert shows up on the doctor dashboard right away. Alerts never wait. |
| UC4 | Review a result | Doctor | The doctor sees the patients sorted by severity, opens a report with the SpO₂ chart and approves or corrects the result. Every decision is logged. |
| UC5 | Adapt to carbon intensity | Carbon scheduler | With high carbon intensity (simulated), the analysis waits for cleaner electricity but is done before 08:00; close to the deadline it uses the fast model. It can also move to a node in a cleaner (simulated) region. With low carbon intensity, the accurate model is used. |
| UC6 | Scale under load | Kubernetes | When a lot of nights come in at the same time, Kubernetes starts more apnea-detector instances and removes them again later. |
| UC7 | Monitor the system | Team (developers) | A dashboard shows response times, running instances, which model was used and how much CO₂ each analysis needed. |

---

## Component diagram

![Component diagram](diagrams/30.10_B_component-diagram_v3.png)

Zoomable version: [diagrams/30.10_B_component-diagram_v3.md](diagrams/30.10_B_component-diagram_v3.md)

The flow of one night: `device-simulator` → **raw-signals** → `apnea-detector` → **apnea-events** → `ahi-triage` → **night-results** → `doctor-dashboard`.

### Microservices

We have six microservices. The device-simulator stands for the patients' homes, the other five run in Kubernetes.

| Microservice | Use cases | What it does | Its data | Owner |
| --- | --- | --- | --- | --- |
| `device-simulator` | UC1, UC6 | Creates one night of SpO₂ and breathing data for each of the 5 patients and sends it to Kafka (one message per minute). A burst mode sends many nights at once for the scaling demo. | – (synthetic data) | Aliénor |
| `apnea-detector` | UC1, UC2, UC3, UC5, UC6 | Reads `raw-signals`, cleans the data and saves the raw night. Finds apnea events with the fast or the accurate model (chosen by the carbon mode), measures CO₂ with CodeCarbon and sends one `apnea-events` message per minute. A separate alert check (own consumer group, never paused) sends a ZeroMQ alert if SpO₂ < 80 %. Scales 1 → 3 pods. | PostgreSQL: `raw_nights` | Barbara |
| `ahi-triage` | UC2 | Counts the events of a night. After the last minute it calculates the AHI and severity, saves the result and sends `night-results`. | PostgreSQL: `results` | Aliénor |
| `alert-service` | UC3 | Gets urgent alerts over ZeroMQ and saves them for the dashboard. | PostgreSQL: `alerts` | Barbara |
| `doctor-dashboard` | UC3, UC4 | Shows the patients sorted by severity, SpO₂ charts and alerts. The doctor approves or corrects each result; every decision goes into the audit log. | PostgreSQL: `decisions` (audit log) | Aliénor |
| `carbon-scheduler` | UC5 | Reads the (simulated) carbon intensity, sets `low_carbon` or `high_carbon` mode in etcd, delays the analysis until cleaner electricity (deadline 08:00) and moves the detector pod to a cleaner node (AT / NO / PL). | etcd: carbon mode | Barbara |

**AI model:** the AI model is not a separate microservice. It is part of the `apnea-detector`, which loads a scikit-learn model (`models/model.joblib`, path from `MODEL_PATH`). We train it beforehand with a training script on simulated nights; the script prints the F1 score and the CO₂ of the training.

### Other components

| Component | Why we need it |
| --- | --- |
| **Kafka** (3 brokers, KRaft) | Carries the three topics `raw-signals` (3 partitions), `apnea-events` and `night-results`. Every message is stored 3 times and kept 7 days, so a night can wait for low-carbon electricity and one broker can fail without data loss. Message key = `patient_id`. |
| **ZeroMQ** | Direct, fast channel for urgent alerts, so they never wait in a queue. |
| **etcd** | Stores the current carbon mode (`/sleep-apnea/carbon_mode`). The scheduler writes it, the detector reads it – the detector keeps working even if the scheduler is down. |
| **PostgreSQL** | One database with 5 tables; each table is written by only one service. |
| **Kubernetes** | kind locally, GKE Standard on Google Cloud. Nodes are labelled AT / NO / PL (simulated regions). The HPA scales the apnea-detector from 1 to 3 pods. |
| **Prometheus + Grafana** | All services expose `/metrics`; with the Kafka exporter we see health, latency, Kafka lag, pods, the model used and CO₂. |
| **GitHub Actions** | Tests, builds the images and pushes them to Artifact Registry. |

---

## Data model and message model

![Data model and message model](diagrams/30.10_B_data-message-model_v1.png)

Zoomable version: [diagrams/30.10_B_data-message-model_v1.md](diagrams/30.10_B_data-message-model_v1.md)

We only need five simple tables in one PostgreSQL database (`patients`, `raw_nights`, `results`, `alerts`, `decisions`), and each table is written by just one service. Patients have a label (e.g. *Patient 1*), no real name. Between the services we send four kinds of messages: three over Kafka (`raw-signals`, `apnea-events`, `night-results`) and the alert over ZeroMQ.

---

## Sequence diagram – one night end to end (UC1–UC7)

![Sequence diagram](diagrams/30.10_B_sequence-diagram_v2.png)

Zoomable version: [diagrams/30.10_B_sequence-diagram_v2.md](diagrams/30.10_B_sequence-diagram_v2.md)

The night comes in minute by minute: the apnea-detector checks every minute for a dangerous SpO₂ drop, and the carbon mode decides if it runs the accurate model, pauses the analysis or uses the fast model close to 08:00. After the last minute, ahi-triage calculates the AHI and the doctor approves or corrects it, and when many nights come at once Kubernetes scales the detector from 1 to 3 pods.

---

## Repository structure

```
ADR/        architecture decision records (in the order we made them)
diagrams/   component, data/message model and sequence diagrams (.mmd source, .png, .md to zoom)
doc/        project summary (PDF)
requirements.txt   pinned Python libraries for all services (see below)
```

Older diagram versions (`24.10_A_…_v1`, `27.10_B_…_v2`, `30.10_sequence_diagram`) are kept to show how the design changed; the `30.10_B_*` files are the current ones.

## Status

Design phase: use cases, architecture, data model and decisions are done. Next: Kafka locally (docker-compose), then the services.

---

## Getting started – Python virtual environment

All services are written in Python 3.11+. The libraries they need (Kafka, PostgreSQL, ZeroMQ, etcd, Kubernetes API, Prometheus metrics, CodeCarbon, scikit-learn, FastAPI, pytest) are pinned in [`requirements.txt`](requirements.txt), so we both work with the same versions. Kafka, PostgreSQL, etcd, Prometheus and Grafana themselves run as containers in the cluster, not in the venv.

Create the virtual environment once, from the repository root:

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Next time, only activate it again (second line). `(.venv)` in front of the prompt shows it is active; `deactivate` leaves it. Check the install with `python -c "import confluent_kafka; print(confluent_kafka.version())"`. The `.venv/` folder is not committed; when a library is added, pin it in `requirements.txt` and run `pip install -r requirements.txt` again.
