-- decisions: audit log of the doctor's review, written by doctor-dashboard (Aliénor)
-- runs after 03_results.sql, because result_id points to results
-- rows are only inserted, never updated or deleted (audit log)

CREATE TABLE IF NOT EXISTS decisions (
    decision_id         BIGSERIAL PRIMARY KEY,
    result_id           BIGINT NOT NULL REFERENCES results(result_id),

    doctor              TEXT NOT NULL,           -- pseudonym, e.g. dr_demo
    action              TEXT NOT NULL CHECK (action IN ('approve', 'correct')),
    corrected_severity  TEXT CHECK (corrected_severity IN ('normal', 'mild', 'moderate', 'severe')),
    comment             TEXT,

    created_at          TIMESTAMPTZ DEFAULT now(),

    -- a correction must say the new severity, an approval must not
    CONSTRAINT decisions_correction_has_severity CHECK (
        (action = 'correct' AND corrected_severity IS NOT NULL)
     OR (action = 'approve' AND corrected_severity IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS decisions_result_id_idx ON decisions (result_id);
