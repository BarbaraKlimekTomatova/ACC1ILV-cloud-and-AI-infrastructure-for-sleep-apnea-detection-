-- results: one row per analysed night, written by ahi-triage (Barbara)
-- runs after 02_raw_nights.sql, because night_id points to raw_nights

CREATE TABLE IF NOT EXISTS results (
    result_id      BIGSERIAL PRIMARY KEY,
    night_id       TEXT NOT NULL REFERENCES raw_nights(night_id),

    -- the result for the doctor
    ahi            REAL CHECK (ahi >= 0),                       -- events per hour
    severity       TEXT CHECK (severity IN ('normal', 'mild', 'moderate', 'severe')),
    event_count    INT  CHECK (event_count >= 0),

    -- which model ran and how
    model          TEXT CHECK (model IN ('fast', 'accurate')),
    model_version  TEXT,                                        -- same text as model_versions.version
    carbon_mode    TEXT CHECK (carbon_mode IN ('low_carbon', 'high_carbon')),
    region         TEXT CHECK (region IN ('AT', 'NO', 'PL')),

    -- CO2 of the analysis (CodeCarbon)
    kwh            REAL CHECK (kwh >= 0),
    gco2           REAL CHECK (gco2 >= 0),
    deadline_met   BOOLEAN,                                     -- ready before 08:00?

    -- short text summary from the LLM
    llm_summary    TEXT,
    llm_model      TEXT,
    llm_gco2       REAL CHECK (llm_gco2 >= 0),

    created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS results_night_id_idx ON results (night_id);