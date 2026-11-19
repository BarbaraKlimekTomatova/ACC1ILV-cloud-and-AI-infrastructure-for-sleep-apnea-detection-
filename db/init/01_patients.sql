-- patients: one row per (fictional) patient, written by the seed script (Aliénor)
-- runs first, because raw_nights.patient_id points to patients
-- GDPR: all data is fictional and pseudonymised; no real names, only P01..P05

CREATE TABLE IF NOT EXISTS patients (
    patient_id     TEXT PRIMARY KEY,             -- P01 .. P05
    label          TEXT NOT NULL,                -- shown on the dashboard, e.g. "Patient 01"
    source_record  TEXT UNIQUE,                  -- PhysioNet record used for the nights, e.g. ucddb018

    -- patient card on the night detail page
    age            INT  CHECK (age BETWEEN 0 AND 120),
    sex            TEXT CHECK (sex IN ('F', 'M')),
    bmi            REAL CHECK (bmi BETWEEN 10 AND 80),
    diagnosis      TEXT,                         -- reason for referral
    comorbidities  TEXT,
    medications    TEXT,
    notes          TEXT,                         -- e.g. Epworth score

    created_at     TIMESTAMPTZ DEFAULT now()
);
