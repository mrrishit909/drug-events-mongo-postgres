-- Indexes for the two access paths: from a drug to its reports, and from a reaction to its reports.
CREATE INDEX report_drug_drug ON report_drug (drug, report_id) WHERE role = 1;    -- suspect drugs only
CREATE INDEX report_reaction_pt ON report_reaction (pt, report_id);
ANALYZE;
