-- carbon_decisions: what the carbon-scheduler did and why, written by carbon-scheduler (Aliénor)
-- no foreign keys

CREATE TABLE IF NOT EXISTS carbon_decisions (
    id                BIGSERIAL PRIMARY KEY,
    at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    action            TEXT NOT NULL CHECK (action IN ('pause', 'resume', 'move', 'scale')),
    region            TEXT CHECK (region IN ('AT', 'NO', 'PL')),  -- target region (for move)
    carbon_intensity  REAL CHECK (carbon_intensity >= 0),         -- gCO2/kWh at decision time
    reason            TEXT                                        -- e.g. "intensity 420 > 300, deadline in 6 h"
);

CREATE INDEX IF NOT EXISTS carbon_decisions_at_idx ON carbon_decisions (at);
