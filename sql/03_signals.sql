-- Step 4: disproportionality screening, the standard first pass in pharmacovigilance.
-- For each suspect drug and reaction, compare how often the reaction is reported with this drug against all other drugs.
--              reaction   other reactions
--   drug          a            b
--   other drugs   c            d
-- PRR = [a/(a+b)] / [c/(c+d)];  ROR = ad/bc with a 95% CI;  signal (Evans 2001): a >= 3, PRR >= 2, chi-square >= 4.
-- Counts are reports, not rows: a report naming a drug twice, or a reaction twice, counts once.
-- Reports naming more than 5 distinct suspect drugs (2.2%; one lists 1,406 suspect rows) are left out of the main
-- screen: each pairs every drug with every reaction and they produced most of the signals. screen_sensitivity keeps both.
DROP TABLE IF EXISTS pair, signal, screen_sensitivity;
CREATE TABLE pair AS
SELECT DISTINCT d.drug, x.pt, d.report_id
  FROM report_drug d JOIN report_reaction x USING (report_id)
 WHERE d.role = 1 AND d.drug IS NOT NULL AND x.pt IS NOT NULL;
ALTER TABLE pair ADD COLUMN suspects integer;
UPDATE pair p SET suspects = s.n
  FROM (SELECT report_id, count(DISTINCT drug) AS n FROM report_drug WHERE role = 1 AND drug IS NOT NULL GROUP BY 1) s
 WHERE s.report_id = p.report_id;

CREATE FUNCTION pg_temp.screen(max_suspects integer)
RETURNS TABLE (drug text, pt text, a int, b int, c int, d int, prr numeric, ror numeric, ror_lower95 numeric, chi2_yates numeric)
LANGUAGE sql AS $$
  WITH p AS (SELECT * FROM pair WHERE suspects <= max_suspects),
       n AS (SELECT count(DISTINCT report_id)::numeric AS n FROM p),
       drug_n AS (SELECT drug, count(DISTINCT report_id)::numeric AS n_drug FROM p GROUP BY drug),
       pt_n AS (SELECT pt, count(DISTINCT report_id)::numeric AS n_pt FROM p GROUP BY pt),
       ab AS (SELECT drug, pt, count(*)::numeric AS a FROM p GROUP BY drug, pt),
       t AS (SELECT ab.drug, ab.pt, a, n_drug - a AS b, n_pt - a AS c, n.n - n_drug - n_pt + a AS d, n.n
               FROM ab JOIN drug_n USING (drug) JOIN pt_n USING (pt) CROSS JOIN n WHERE a >= 3)
  SELECT drug, pt, a::int, b::int, c::int, d::int,
         round((a / (a + b)) / nullif(c / (c + d), 0), 3),
         round((a * d) / nullif(b * c, 0), 3),
         round(exp(ln((a * d) / nullif(b * c, 0)) - 1.96 * sqrt(1 / a + 1 / nullif(b, 0) + 1 / nullif(c, 0) + 1 / nullif(d, 0))), 3),
         round(n * power(greatest(abs(a * d - b * c) - n / 2, 0), 2) / nullif((a + b) * (c + d) * (a + c) * (b + d), 0), 2)
    FROM t
$$;

CREATE TABLE signal AS SELECT *, (prr >= 2 AND chi2_yates >= 4) AS is_signal FROM pg_temp.screen(5);

CREATE TABLE screen_sensitivity AS
SELECT 'reports with at most 5 suspect drugs' AS screen, (SELECT count(DISTINCT report_id) FROM pair WHERE suspects <= 5) AS reports,
       count(*) AS pairs_with_3_reports, count(*) FILTER (WHERE is_signal) AS signals FROM signal
UNION ALL
SELECT 'all reports', (SELECT count(DISTINCT report_id) FROM pair), count(*), count(*) FILTER (WHERE prr >= 2 AND chi2_yates >= 4)
  FROM pg_temp.screen(100000);
