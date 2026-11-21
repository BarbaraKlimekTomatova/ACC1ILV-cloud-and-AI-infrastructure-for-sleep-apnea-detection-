-- raw_nights: one row per recorded night, written by the apnea-detector (Barbara)
-- runs after 01_patients.sql, because patient_id points to patients

CREATE TABLE IF NOT EXISTS raw_nights (
    night_id     TEXT PRIMARY KEY,                             -- e.g. ucddb013
    patient_id   TEXT NOT NULL REFERENCES patients(patient_id),
    source       TEXT CHECK (source IN ('ucddb', 'apnea-ecg')), -- PhysioNet dataset
    recorded_at  TIMESTAMPTZ DEFAULT now(),                    -- when the row was written

    -- signals of the whole night as JSON arrays
    spo2         JSONB CHECK (jsonb_typeof(spo2)    = 'array'), -- 1 Hz, %
    flow         JSONB CHECK (jsonb_typeof(flow)    = 'array'), -- 4 Hz
    thorax       JSONB CHECK (jsonb_typeof(thorax)  = 'array'), -- 4 Hz
    abdomen      JSONB CHECK (jsonb_typeof(abdomen) = 'array')  -- 4 Hz
);

CREATE INDEX IF NOT EXISTS raw_nights_patient_id_idx ON raw_nights (patient_id);