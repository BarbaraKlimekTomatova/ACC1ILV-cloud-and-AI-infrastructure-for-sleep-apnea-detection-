-- alerts: one row per urgent alert (SpO2 < 80 %), written by alert-service (Aliénor)
-- runs after 02_raw_nights.sql, because night_id points to raw_nights

CREATE TABLE IF NOT EXISTS alerts (
    alert_id     BIGSERIAL PRIMARY KEY,
    night_id     TEXT NOT NULL REFERENCES raw_nights(night_id),

    minute       INT  NOT NULL CHECK (minute >= 0),            -- minute of the night
    spo2_min     REAL NOT NULL CHECK (spo2_min BETWEEN 0 AND 100), -- lowest SpO2 in that minute, %

    detected_at  TIMESTAMPTZ NOT NULL,           -- when alert-service saw the drop
    stored_at    TIMESTAMPTZ DEFAULT now()       -- when the row was written (latency = stored_at - detected_at)
);

CREATE INDEX IF NOT EXISTS alerts_night_id_idx ON alerts (night_id);
