-- 7 database users, one per service (ADR 0007)
-- every user can READ all tables, but WRITE only its own table
-- passwords below are for local development only; in Kubernetes they come from Secrets

DO $$
DECLARE
    u RECORD;
BEGIN
    FOR u IN SELECT * FROM (VALUES
        ('patient_seed',     'dev_patient_seed'),
        ('apnea_detector',   'dev_apnea_detector'),
        ('ahi_triage',       'dev_ahi_triage'),
        ('model_trainer',    'dev_model_trainer'),
        ('alert_service',    'dev_alert_service'),
        ('doctor_dashboard', 'dev_doctor_dashboard'),
        ('carbon_scheduler', 'dev_carbon_scheduler')
    ) AS t(name, pw)
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = u.name) THEN
            EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', u.name, u.pw);
        END IF;
        EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), u.name);
        EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', u.name);
        EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', u.name);
    END LOOP;
END $$;

-- nobody may create tables or other objects except the admin
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- write rights: one owner per table
GRANT INSERT, UPDATE ON patients       TO patient_seed;
GRANT INSERT, UPDATE ON raw_nights     TO apnea_detector;
GRANT INSERT, UPDATE ON results        TO ahi_triage;
GRANT INSERT, UPDATE ON model_versions TO model_trainer;
GRANT INSERT         ON alerts           TO alert_service;     -- alerts are never changed
GRANT INSERT         ON decisions        TO doctor_dashboard;  -- audit log: insert only
GRANT INSERT         ON carbon_decisions TO carbon_scheduler;  -- log: insert only

-- BIGSERIAL columns need the sequence
GRANT USAGE ON SEQUENCE results_result_id_seq      TO ahi_triage;
GRANT USAGE ON SEQUENCE alerts_alert_id_seq        TO alert_service;
GRANT USAGE ON SEQUENCE decisions_decision_id_seq  TO doctor_dashboard;
GRANT USAGE ON SEQUENCE carbon_decisions_id_seq    TO carbon_scheduler;
