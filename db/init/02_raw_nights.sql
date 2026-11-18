-- raw_nights: one row per night, written by the apnea-detector (Barbara)
-- runs after 01_patients.sql, because patient_id points to patients

CREATE TABLE IF NOT EXISTS raw_nights (
    night_id     TEXT PRIMARY KEY,
    patient_id   TEXT NOT NULL REFERENCES patients(patient_id),
    source       TEXT,                       -- ucddb or apnea-ecg
    recorded_at  TIMESTAMPTZ DEFAULT now(),

    -- signals of the whole night as arrays
    spo2         JSONB,        -- 1 Hz, %
    flow         JSONB,        -- 4 Hz
    thorax       JSONB,        -- 4 Hz
    abdomen      JSONB         -- 4 Hz
);
