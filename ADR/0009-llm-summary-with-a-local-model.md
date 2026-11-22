# ADR 0009: LLM summary for the doctor with a small local model

- **Status:** Accepted
- **Date:** 22.11.2026
- **Use cases:** UC2 (step 8, alternative flow A4), UC4

## Context
For every analysed night ahi-triage writes a short text for the doctor (`results.llm_summary`, UC2 step 8),
so the dashboard does not only show numbers. The night belongs to a patient, so health data must not leave
our system without need (GDPR). Every LLM call also uses energy, and the result must not wait for the LLM
or get lost when the LLM is down.

## Options
1. **External LLM API** (e.g. a large cloud model): best text, but the data leaves our system, it needs an
   API key and internet, and we cannot measure its energy.
2. **No LLM, a fixed text template:** no energy, no risk, but no AI part and less readable for the doctor.
3. **Small local model with Ollama** (`llama3.2:1b`, 1.3 GB), like course exercise 7.

## Decision
We use option 3.
- ahi-triage calls Ollama (`LLM_URL`, `/api/generate`) once per finished night, with temperature 0.
- **Privacy:** the prompt contains only numbers (hours, AHI, severity, apnea and hypopnea minutes), never
  the patient id or name. The model runs on our own machine, nothing goes to the internet.
- **The model words, it does not decide:** the urgency ("review soon" for moderate and severe, otherwise
  "routine review") is set in our code and given to the model, because a 1B model invents things.
- **CO₂ of each call:** Ollama's run time × `LLM_WATTS` (default 30 W) × the carbon intensity of the night,
  stored as `llm_gco2` (same method as ADR 0010). Prometheus: `triage_llm_gco2_total`, `triage_llm_failed_total`.
- **If Ollama does not answer** within `LLM_TIMEOUT_S` (60 s): the result is saved and sent without
  summary (UC2 A4).

## Consequences
- No patient data leaves the system, no API key and no extra cost.
- A summary costs about 0.0001–0.0005 gCO₂, in the same range as the analysis of a whole night, so we
  can show it next to the analysis in Grafana.
- The text of a 1B model is simple and can contain small mistakes. The numbers in `results` stay the truth;
  the text is only a help for the doctor.
- Ollama is one more process to run (laptop locally, a Deployment in Kubernetes later).
- **Sustainability trade-off:** a model 100 times smaller than a cloud LLM, one call per night (not per
  minute), and the summary can be switched off with `USE_LLM=0`.
