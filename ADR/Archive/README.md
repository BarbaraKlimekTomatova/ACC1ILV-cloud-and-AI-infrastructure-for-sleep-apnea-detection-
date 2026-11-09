# Archived ADRs (before checkpoint 1 feedback)

> These are our first 28 ADRs. After the feedback we kept only 7 real architectural decisions, see [../README.md](../README.md). We keep these to show how the design changed.

One file = one decision. The ADRs follow the order in which we made the decisions in this repo:
- **24.10** – component diagram v1 (`diagrams/24.10_A_component-diagram_v1.mmd`)
- **27.10** – component diagram v2 (`diagrams/27.10_B_component flowchart diagram_v2_update.mmd`)
- **30.10** – sequence diagram v1 (`diagrams/30.10_sequence_diagram.mmd` (by Aliénor))
- **30.10** – project summary: component diagram v3, data/message model and sequence diagram v2 (`diagrams/30.10_B_*`)

| # | Date | Decision | Status | Use cases |
| --- | --- | --- | --- | --- |
| 0001 | 24.10.2026 | [Microservices on Kubernetes](0001-microservices-on-kubernetes.md) | Superseded by ADR 0008 | UC1–UC7 |
| 0002 | 24.10.2026 | [Kafka with three topics for the main pipeline](0002-kafka-with-three-topics-for-the-main-pipeline.md) | Accepted (extended by ADR 0016 and 0020) | UC1, UC2 |
| 0003 | 24.10.2026 | [One PostgreSQL database with separate tables per service](0003-one-postgresql-database-with-separate-tables-per-service.md) | Accepted (made more exact in ADR 0025) | UC1–UC4 |
| 0004 | 24.10.2026 | [Monitoring with Prometheus and Grafana](0004-monitoring-with-prometheus-and-grafana.md) | Superseded by ADR 0017 | UC7 |
| 0005 | 24.10.2026 | [Analysis service asks the carbon-scheduler by REST](0005-analysis-service-asks-the-carbon-scheduler-by-rest.md) | Superseded by ADR 0010 | UC5 |
| 0006 | 24.10.2026 | [Replay PhysioNet nights in the device-simulator](0006-replay-physionet-nights-in-the-device-simulator.md) | Superseded by ADR 0012 | UC1 |
| 0007 | 24.10.2026 | [The doctor reviews and approves every result](0007-the-doctor-reviews-and-approves-every-result.md) | Accepted | UC4 |
| 0008 | 27.10.2026 | [Six microservices, aligned with the proposal](0008-six-microservices-aligned-with-the-proposal.md) | Accepted | UC1–UC7 |
| 0009 | 27.10.2026 | [Urgent alerts over ZeroMQ to a separate alert-service](0009-urgent-alerts-over-zeromq-to-a-separate-alert-service.md) | Accepted (made exact in ADR 0022) | UC3 |
| 0010 | 27.10.2026 | [Carbon mode stored in etcd](0010-carbon-mode-stored-in-etcd.md) | Accepted (names changed in ADR 0021) | UC5 |
| 0011 | 27.10.2026 | [Carbon-scheduler moves the detector pod between node pools](0011-carbon-scheduler-moves-the-detector-pod-between-node-pools.md) | Accepted | UC5 |
| 0012 | 27.10.2026 | [Synthetic nights instead of replaying PhysioNet](0012-synthetic-nights-instead-of-replaying-physionet.md) | Accepted | UC1, UC6 |
| 0013 | 27.10.2026 | [Fast or accurate model, CO₂ measured with CodeCarbon](0013-fast-or-accurate-model-co2-measured-with-codecarbon.md) | Accepted (training in ADR 0023) | UC2, UC5 |
| 0014 | 27.10.2026 | [Autoscaling the apnea-detector with HPA (1–3 pods)](0014-autoscaling-the-apnea-detector-with-hpa-1-3-pods.md) | Accepted | UC6 |
| 0015 | 27.10.2026 | [kind cluster for local development](0015-kind-cluster-for-local-development.md) | Accepted (cloud in ADR 0024) | UC1–UC7 |
| 0016 | 27.10.2026 | [Kafka with one broker](0016-kafka-with-one-broker.md) | Superseded by ADR 0020 | UC1, UC2 |
| 0017 | 27.10.2026 | [Simpler monitoring](0017-simpler-monitoring.md) | Accepted | UC7 |
| 0018 | 27.10.2026 | [Remove direct links that skip the pipeline](0018-remove-direct-links-that-skip-the-pipeline.md) | Accepted | UC1, UC4 |
| 0019 | 30.10.2026 | [One sequence diagram for one night, colour-coded by data type](0019-one-sequence-diagram-for-one-night-colour-coded-by-data-type.md) | Superseded by ADR 0028 | UC1–UC5, UC7 |
| 0020 | 30.10.2026 | [Kafka cluster with 3 brokers](0020-kafka-cluster-with-3-brokers.md) | Accepted | UC1, UC2, UC5 |
| 0021 | 30.10.2026 | [Carbon modes are called low_carbon and high_carbon](0021-carbon-modes-are-called-low-carbon-and-high-carbon.md) | Accepted | UC5 |
| 0022 | 30.10.2026 | [Alert check uses its own Kafka consumer group](0022-alert-check-uses-its-own-kafka-consumer-group.md) | Accepted | UC3, UC5 |
| 0023 | 30.10.2026 | [AI model trained offline and loaded from a file](0023-ai-model-trained-offline-and-loaded-from-a-file.md) | Accepted | UC2 |
| 0024 | 30.10.2026 | [Google Cloud GKE Standard with self-hosted Kafka and PostgreSQL](0024-google-cloud-gke-standard-with-self-hosted-kafka-and-postgresql.md) | Accepted | UC5, UC6 |
| 0025 | 30.10.2026 | [Five tables, each written by one service](0025-five-tables-each-written-by-one-service.md) | Accepted (to confirm with the professor) | UC1–UC4 |
| 0026 | 30.10.2026 | [Fixed JSON schemas for messages](0026-fixed-json-schemas-for-messages.md) | Accepted | UC1, UC2, UC3 |
| 0027 | 30.10.2026 | [CI/CD with GitHub Actions](0027-ci-cd-with-github-actions.md) | Accepted | – |
| 0028 | 30.10.2026 | [Sequence diagram v2: all use cases and alternative paths](0028-sequence-diagram-v2-all-use-cases-and-alternative-paths.md) | Accepted | UC1–UC7 |

## How to add a new ADR

Copy a file, use the next number and the date. Never change an accepted ADR: write a new one and set the old one to *Superseded by ADR xxxx*.
