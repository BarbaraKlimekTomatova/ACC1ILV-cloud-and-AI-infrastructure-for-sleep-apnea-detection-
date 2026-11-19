-- 5 demo patients P01..P05, each linked to one UCDDB night from PhysioNet
-- age, sex, BMI, diagnosis, comorbidities, medications and notes are FICTIONAL (GDPR)
-- order goes roughly from few to many apnea minutes in the source record

INSERT INTO patients
    (patient_id, label, source_record, age, sex, bmi, diagnosis, comorbidities, medications, notes)
VALUES
    ('P01', 'Patient 01', 'ucddb018', 41, 'F', 24.8,
     'Suspected OSA: snoring reported by partner',
     'None',
     'None',
     'Epworth 7/24; non-smoker'),

    ('P02', 'Patient 02', 'ucddb017', 52, 'M', 28.9,
     'Suspected OSA: daytime sleepiness, witnessed pauses',
     'Hypertension',
     'Ramipril 5 mg',
     'Epworth 11/24; 2 coffees per day'),

    ('P03', 'Patient 03', 'ucddb013', 58, 'F', 30.6,
     'Suspected OSA: morning headaches, fatigue',
     'Type 2 diabetes, hypothyroidism',
     'Metformin 1000 mg, Levothyroxine 75 µg',
     'Epworth 12/24'),

    ('P04', 'Patient 04', 'ucddb010', 63, 'M', 33.1,
     'Suspected OSA: loud snoring, nocturia',
     'Hypertension, atrial fibrillation',
     'Amlodipine 5 mg, Apixaban 5 mg',
     'Epworth 15/24; drives for work'),

    ('P05', 'Patient 05', 'ucddb025', 49, 'M', 36.4,
     'Suspected severe OSA: falls asleep while driving',
     'Obesity, hypertension, GERD',
     'Losartan 50 mg, Pantoprazole 20 mg',
     'Epworth 18/24; urgent referral')
ON CONFLICT (patient_id) DO NOTHING;
