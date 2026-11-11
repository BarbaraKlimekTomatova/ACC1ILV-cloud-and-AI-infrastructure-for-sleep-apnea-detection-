# Architecture Decision Records

After the checkpoint 1 feedback we kept only the decisions that really shape our architecture. Small technology choices (kind, JSON schemas, synthetic data …) are in the main README. Our first 28 ADRs are in [Archive/](Archive/README.md).

| # | Decision | Use cases |
| --- | --- | --- |
| [0001](0001-kafka-as-a-buffer-for-time-shifting.md) | Kafka as a buffer for time-shifting | UC1, UC2, UC5 |
| [0002](0002-separate-alert-path-that-never-waits.md) | Separate alert path that never waits | UC3, UC5 |
| [0003](0003-carbon-aware-strategy.md) | Carbon-aware strategy | UC2, UC5 |
| [0004](0004-carbon-aware-redeployment.md) | Carbon-aware redeployment | UC5 |
| [0005](0005-model-lifecycle-carbon-aware-retraining.md) | Model lifecycle – carbon-aware retraining | UC7, UC2 |
| [0006](0006-monitoring-system-and-ai-behaviour.md) | Monitoring of system health and AI behaviour | UC6 |
| [0007](0007-one-postgresql-database-with-table-ownership.md) | One PostgreSQL database, each table owned by one service | UC1–UC4 |

Each ADR has: context, options, decision and consequences (including the sustainability trade-offs).
