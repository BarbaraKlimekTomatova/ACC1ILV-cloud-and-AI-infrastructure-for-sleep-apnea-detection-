# ADR 0012: Synthetic nights instead of replaying PhysioNet

- **Date:** 27.10.2026
- **Status:** Accepted
- **Source:** `diagrams/27.10_B_component flowchart diagram_v2_update.mmd`
- **Use cases:** UC1, UC6

## Context
Converting PhysioNet data is a lot of work, and we need exact control of the events for the demo (e.g. an SpO₂ drop below 80 %).

## Decision
The device-simulator generates synthetic nights for 5 patients. PhysioNet stays optional. Supersedes ADR 0006.

## Alternatives
Keep PhysioNet: more realistic, but slower to build and harder to control.

## Consequences
Fast to build and fully controllable. The message format stays the same if we switch to PhysioNet later.
