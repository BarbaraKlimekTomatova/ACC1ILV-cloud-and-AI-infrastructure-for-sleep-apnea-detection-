# ADR 0007: The doctor reviews and approves every result

- **Date:** 24.10.2026
- **Status:** Accepted
- **Source:** `diagrams/24.10_A_component-diagram_v1.mmd`
- **Use cases:** UC4

## Context
The system only screens. A diagnosis must come from a doctor.

## Decision
The dashboard shows the result to the doctor, who approves or corrects it. Every decision is saved (audit log).

## Alternatives
Send the result straight to the patient: faster, but not safe.

## Consequences
Human in the loop and a clear audit trail. The doctor's step is part of the demo.
