-- model_versions: one row per trained model, written by model-trainer (Barbara)
-- results.model_version holds the same text as model_versions.version

CREATE TABLE IF NOT EXISTS model_versions (
    version         TEXT PRIMARY KEY,                               -- e.g. accurate-v3
    model           TEXT NOT NULL CHECK (model IN ('fast', 'accurate')),
    trained_at      TIMESTAMPTZ DEFAULT now(),                      -- when the training finished
    train_nights    INT  CHECK (train_nights >= 0),                 -- how many nights were used
    doctor_corrections_used INT  CHECK (doctor_corrections_used >= 0),  -- how many doctor corrections (decisions.action = correct) were used
    triggered_by    TEXT CHECK (triggered_by IN ('schedule', 'manual', 'drift')),  -- weekly CronJob, team, or monitoring

    -- quality on the held-out Apnea-ECG nights
    f1              REAL CHECK (f1 BETWEEN 0 AND 1),
    precision_score REAL CHECK (precision_score BETWEEN 0 AND 1),
    recall_score    REAL CHECK (recall_score BETWEEN 0 AND 1),

    -- CO2 of the training (CodeCarbon)
    kwh             REAL CHECK (kwh >= 0),
    gco2            REAL CHECK (gco2 >= 0),
    region          TEXT CHECK (region IN ('AT', 'NO', 'PL')),

    -- F1 gate in CI/CD
    status          TEXT DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected')),
    artifact_path   TEXT                                            -- where the model file is stored
);