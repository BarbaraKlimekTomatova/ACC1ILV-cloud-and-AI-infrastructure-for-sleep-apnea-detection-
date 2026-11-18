-- results: one row per analysed night, written by ahi-triage
-- runs after 02_raw_nights.sql, because night_id points to raw_nights

CREATE TABLE IF NOT EXISTS results (
    result_id      BIGSERIAL PRIMARY KEY,
    night_id       TEXT NOT NULL REFERENCES raw_nights(night_id),

    -- the result for the doctor
    ahi            REAL,                     -- events per hour
    severity       TEXT,                     -- normal, mild, moderate, severe
    event_count    INT,

    -- which model ran and how
    model          TEXT,                     -- fast or accurate
    model_version  TEXT,
    carbon_mode    TEXT,                     -- low_carbon or high_carbon
    region         TEXT,                     -- AT, NO or PL

    -- CO2 of the analysis (CodeCarbon)
    kwh            REAL,
    gco2           REAL,
    deadline_met   BOOLEAN,                  -- ready before 08:00?

    -- short text summary from the LLM
    llm_summary    TEXT,
    llm_model      TEXT,
    llm_gco2       REAL,

    created_at     TIMESTAMPTZ DEFAULT now()
);
