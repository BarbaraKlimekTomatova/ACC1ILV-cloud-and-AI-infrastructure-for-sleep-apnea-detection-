# Measured CO₂ and sustainability trade-offs

For the presentation (one slide): what one part of the system costs in gCO₂ and what we gain or lose for it.
Team member 1 part (Barbara): training, one night in the detector, the LLM summary and the AHI effect.
Team member 2 part (Aliénor): the model comparison script and the effect of waiting / moving region
(`carbon_decisions`), added below when ready.

## 1. gCO₂ per step

| Step | How it is measured | Value | Source |
| --- | --- | ---: | --- |
| Training the accurate model (once per new version, UC7) | CodeCarbon around the training (ADR 0010) | **≈ 0.021 g** (0.00019 kWh, 24 s, region AT, MacBook, 25 Nov) | `model_versions.gco2`, `train.py` prints `training energy: ... gCO2` |
| One night in the apnea-detector, accurate model | CPU time × CPU power × carbon intensity | **≈ 0.002–0.003 g** (kind: 0.0015–0.0022, 5 nights = 0.009 g; docker compose 25 Nov: 0.0024–0.0029, 5 nights = 0.013 g) | `detector_gco2_total`, `results.gco2`, [nfr-results.md](nfr-results.md), `scripts/compose-e2e.sh` |
| One night, fast rule (high_carbon) | same | **≈ 50× less for the classification** (below 1 ms instead of about 50 ms CPU per night); the features cost the same in both modes | [model-limits.md](model-limits.md) |
| LLM summary of one night (Ollama, llama3.2:1b) | Ollama run time × `LLM_WATTS` (30 W) × carbon intensity | 🟡 run below (formula: 3 s → 0.0075 g at 300 gCO₂/kWh) | `results.llm_gco2`, `triage_llm_gco2_total` |

Order of size: one training ≈ 10 nights of analysis, and it runs only for a new model version, not every night.
One LLM summary of a few seconds costs about as much as several nights of analysis.
So the LLM is the first thing to switch off in high carbon (`USE_LLM: "0"`), not the accurate model.

## 2. What we gain or lose

| Choice | We save | We lose |
| --- | --- | --- |
| Fast rule instead of the accurate model (high_carbon close to 08:00, ADR 0003) | CPU of the classification (about 50×) | F1 0.906 → 0.832, precision 0.850 → 0.714; no apnea / hypopnea split; AHI too high (ucddb013 moderate → severe, ucddb017 mild → moderate) |
| Wait for low carbon at night (detector pauses) | the night runs at a lower carbon intensity (at 01:00 in the simulation: PL ≈ 750, AT ≈ 380, NO ≈ 40 gCO₂/kWh) | time: the result comes later, still before 08:00 (5 / 5 `deadline_met`) |
| No LLM summary (`USE_LLM: "0"`) | the biggest single item per night | the short text for the doctor; AHI, severity and events stay the same |
| Train only in a low-carbon window (UC7) | training at the cleanest region / hour | a new model version comes later |
| Per-minute AHI instead of a sleep lab | no EEG, one cheap model per minute | AHI lower than clinical (ucddb025 94 → 54), screening only |

## 3. Measure the missing numbers (on the laptop)

```
source .venv312/bin/activate
pip install codecarbon==3.3.2
python services/model-trainer/train.py --no-db --version co2-check --out /tmp/co2-check.joblib
```
The last lines print `training energy: ... kWh, ... gCO2` (`--out` keeps `models/model.joblib` as it is). Put the gCO₂ in the table.

LLM (needs Ollama: `ollama serve`, `ollama pull llama3.2:1b`): run the compose demo with the LLM on,
`USE_LLM: "1"` in `docker-compose.demo.yml`, then `bash scripts/compose-e2e.sh`, then
```
docker compose exec -T postgres psql -U postgres -d sleep_apnea -c "select night_id, round(gco2::numeric,4) as gco2, round(llm_gco2::numeric,4) as llm_gco2 from results order by created_at desc limit 5"
```

## 4. Limits of these numbers

- Detector and LLM are estimates (power × time × simulated carbon intensity), only training is measured with CodeCarbon.
- The carbon intensity of AT / NO / PL is simulated by the carbon-scheduler, not live data.
- Values of a few milligrams are below what CodeCarbon can measure exactly; we compare orders of size, not decimals.
