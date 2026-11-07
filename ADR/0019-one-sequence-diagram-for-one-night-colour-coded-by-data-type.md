# ADR 0019: One sequence diagram for one night, colour-coded by data type

- **Date:** 30.10.2026
- **Status:** Superseded by ADR 0028
- **Source:** `diagrams/30.10_sequence_diagram.mmd` (by Aliénor)
- **Use cases:** UC1–UC5, UC7

## Context
The component diagram shows who talks to whom, but not in which order. The professor wants sequence diagrams.

## Decision
One sequence diagram follows one night through the system. It uses exactly the same components and links as component diagram v2. The background colour shows the type of data: grey = carbon, blue = raw signals, red = alert, orange = apnea events, green = night results, yellow = doctor review, purple = metrics.

## Alternatives
One sequence diagram per use case: more detail, but many diagrams to keep in sync.

## Consequences
Easy to read and matches the component diagram. It has no alternative (failure) paths and no scaling (UC6), and it still uses green / dirty.
