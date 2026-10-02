-- Step 3: the relational model. One report has many drugs and many reactions, so each document splits into three tables.
DROP TABLE IF EXISTS signal, pair, report_reaction, report_drug, report;

CREATE TABLE report (
  report_id      text PRIMARY KEY,                 -- FDA safetyreportid
  version        integer NOT NULL,
  received       date,
  country        text,
  reporter       text,                             -- 1 physician, 2 pharmacist, 3 other health professional, 4 lawyer, 5 consumer
  serious        boolean NOT NULL,
  outcomes       text[] NOT NULL,                  -- death, hospitalization, ...
  duplicate_of_other_source boolean NOT NULL,
  age_years      numeric,
  sex            char(1) CHECK (sex IN ('M', 'F')),
  weight_kg      numeric
);

CREATE TABLE report_drug (
  report_id   text NOT NULL REFERENCES report,
  seq         smallint NOT NULL,
  role        smallint CHECK (role IN (1, 2, 3, 4)),  -- 1 suspect, 2 concomitant, 3 interacting, 4 not administered (E2B R3)
  drug        text,
  name_source text CHECK (name_source IN ('openfda', 'substance', 'product')),
  product     text,
  indication  text,
  pharm_class text,
  PRIMARY KEY (report_id, seq)
);

CREATE TABLE report_reaction (
  report_id text NOT NULL REFERENCES report,
  seq       smallint NOT NULL,
  pt        text,                                  -- MedDRA preferred term
  outcome   text,
  PRIMARY KEY (report_id, seq)
);
