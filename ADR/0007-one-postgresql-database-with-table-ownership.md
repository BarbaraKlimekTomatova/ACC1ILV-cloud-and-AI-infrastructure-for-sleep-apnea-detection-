# ADR 0007: One PostgreSQL database, each table owned by one service

- **Status:** Accepted
- **Date:** 09.11.2026
- **Use cases:** UC1, UC2, UC3, UC4

## Context
We store patients, raw nights, results, alerts and the doctor's decisions (audit log). The textbook microservice way is one database per service.

## Options
1. **One database per service:** strong separation, but 5 database instances to run, back up and monitor. More resources and energy for a small system.
2. **One shared database without rules:** simplest, but services start to depend on each other's tables.
3. **One database, but each table is written by only one service.**

## Decision
We use option 3: `patients`, `raw_nights`, `results`, `alerts` and `decisions`. Each table has one owner service; other services only read.

## Consequences
- One instance to run: less resources and energy, easier for our team.
- Clear ownership keeps the services independent enough.
- The database is a shared point of failure; we accept it for this project.
