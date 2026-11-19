-- model_versions: one row per trained model, written by model-trainer (Barbara)
-- results.model_version holds the same text as model_versions.version

CREATE TABLE IF NOT EXISTS model_versions (
    version         TEXT PRIMARY KEY,           -- e.g. accurate-v3
    model           TEXT NOT NULL,              -- fast or accurate
    trained_at      TIMESTAMPTZ DEFAULT now(),
    train_nights    INT,                        -- how many nights were used

    -- quality on the held-out Apnea-ECG nights
    f1              REAL,
    precision_score REAL,
    recall_score    REAL,

    -- CO2 of the training (CodeCarbon)
    kwh             REAL,
    gco2            REAL,
    region          TEXT,                       -- AT, NO or PL

    -- F1 gate in CI/CD
    status          TEXT DEFAULT 'pending',     -- pending, approved or rejected
    artifact_path   TEXT                        -- where the model file is stored
);
