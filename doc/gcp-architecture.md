# Possible architecture on Google Cloud (GCP)

Draft – how our system could run on Google Cloud. Locally we use kind; on GCP we use the same Kubernetes manifests.

## Overview

```
GitHub ──(GitHub Actions)──► Artifact Registry ──► GKE cluster (europe-north1)
                                                   │
   ┌───────────────────────────────────────────────┼──────────────────────────────┐
   │ node pool "system"   : Kafka (Strimzi, 3 brokers), PostgreSQL, Prometheus,    │
   │                        Grafana, carbon-scheduler, ahi-triage, alert-service,  │
   │                        doctor-dashboard, device-simulator                     │
   │ node pools "at", "no", "pl" (label region=AT/NO/PL, simulated regions):       │
   │                        apnea-detector (HPA 1–3 pods), model-trainer Job       │
   └───────────────────────────────────────────────────────────────────────────────┘
                                                   │
                     Cloud Storage (model files) · Load Balancer (dashboard)
```

## GCP services we use

| Need | GCP service | Why |
| --- | --- | --- |
| Run the microservices | **GKE Standard**, one zonal cluster | Standard (not Autopilot) because we need our own node pools and labels to simulate the regions AT / NO / PL. A zonal cluster is cheaper for a course project. |
| Region | **europe-north1 (Finland)** | One of the cleanest European regions: 98 % carbon-free energy and 39 gCO₂eq/kWh (Google data, 2024). For comparison, europe-central2 (Warsaw) has 40 % and 643 gCO₂eq/kWh. |
| Simulated regions | 3 small **node pools** with labels `region=AT/NO/PL` | The carbon-scheduler moves the apnea-detector with a `nodeSelector` (ADR 0004). Real multi-region would need several clusters, which is too complex and expensive for us. |
| Messaging | **Kafka with Strimzi** inside the cluster | 3 brokers, replication factor 3 (ADR 0001). Managed Service for Apache Kafka would be less work, but more expensive. |
| Database | **PostgreSQL** as a StatefulSet with a persistent disk | One database, 5 tables, each written by one service (ADR 0007). Option: Cloud SQL (managed backups, but extra cost). |
| Container images | **Artifact Registry** | GitHub Actions push the images here; GKE pulls them. |
| CI/CD | **GitHub Actions** + Workload Identity Federation | No service account key stored in GitHub. The pipeline tests, builds, checks the F1 score of a new model and deploys. |
| AI model | **Cloud Storage** bucket | The model-trainer Job saves each model version; the detector loads the approved version. |
| Monitoring | **Prometheus + Grafana** in the cluster (kube-prometheus-stack) | System health and AI behaviour (ADR 0006). Option: Google Managed Service for Prometheus. |
| Dashboard access | **Load Balancer** (Kubernetes Service / Ingress) | Only the doctor-dashboard is reachable from outside. |
| Secrets | **Kubernetes Secrets** (option: Secret Manager) | Database password, Kafka credentials. |

## How the carbon-aware part works on GCP

- The **carbon-scheduler** reads the simulated carbon intensity of AT / NO / PL and publishes `low_carbon` / `high_carbon` to the `carbon-signal` topic.
- **Time-shifting:** in `high_carbon` the apnea-detector stops reading, and the nights wait in Kafka until it is cleaner or the 08:00 deadline gets close.
- **Model switching:** fast model in `high_carbon` near the deadline, accurate model in `low_carbon`.
- **Scaling limit:** the scheduler sets the HPA maximum to 1 pod in `high_carbon` and to 3 pods in `low_carbon`.
- **Moving the detector:** the scheduler changes the `nodeSelector` of the detector to the node pool of the cleanest simulated region.
- **Retraining:** the model-trainer Kubernetes Job starts only in a low-carbon window.
- **Alerts never wait:** alert-check and alert-service run on the system node pool, are never paused and are never moved.
- **Measurement:** CodeCarbon measures the CO₂ of every analysis and training. GCP's Carbon Footprint report can show the footprint of the whole project.

## Keeping the cost low

- Small machine types (e.g. e2-standard-2 / e2-medium); Spot VMs for the detector and trainer node pools.
- Node pools for AT / NO / PL can scale to 0 when they are not used.
- Set a budget alert in Cloud Billing; delete the cluster after the demo (everything is recreated from the manifests).

## Out of scope

Real multi-region deployment, patient and doctor login, high availability across zones.
