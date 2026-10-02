"""Steps 4-5: signal detection in PostgreSQL, the same counts as a MongoDB aggregation, and a head-to-head of the two.

    ./venv/bin/python analyze.py   -> results/signals_top.csv, known_signals.csv, profile.json, mongo_vs_sql.json, benchmark.csv
"""
import csv
import io
import json
import subprocess
import time
from pathlib import Path

import pymongo

import load as L

HERE = Path(__file__).parent
R = HERE / "results"
# Reactions in these drugs' US labels (Warnings or Adverse Reactions): a screen that misses them is not working.
KNOWN = [("SEMAGLUTIDE", "NAUSEA"), ("SEMAGLUTIDE", "PANCREATITIS"), ("DUPILUMAB", "CONJUNCTIVITIS"),
         ("LISINOPRIL", "ANGIOEDEMA"), ("WARFARIN", "INTERNATIONAL NORMALISED RATIO INCREASED"),
         ("CLOZAPINE", "NEUTROPHIL COUNT DECREASED"), ("ISOTRETINOIN", "DRY SKIN"), ("LENALIDOMIDE", "NEUTROPENIA"),
         ("ADALIMUMAB", "INJECTION SITE PAIN"), ("METFORMIN", "LACTIC ACIDOSIS")]


def rows(sql):
    cmd = [x for x in L.PSQL if x != "-qAt"] + ["-q", "--csv", "-d", "faers", "-c", sql]      # with a header row
    return list(csv.DictReader(io.StringIO(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)))


def timed_sql(sql, runs=3):
    """Median of psql's own \\timing over `runs` executions in one session (no process start-up in the number)."""
    script = "\\timing on\n" + "\n".join([sql.strip().rstrip(";") + ";"] * runs) + "\n"
    out = subprocess.run([x for x in L.PSQL if x != "-qAt"] + ["-q", "-d", "faers"], input=script, check=True, capture_output=True, text=True).stdout
    ms = sorted(float(line.split()[1]) for line in out.splitlines() if line.startswith("Time: "))
    assert len(ms) == runs, out[-500:]
    return ms[runs // 2] / 1000


def timed_mongo(fn, runs=3):
    t = []
    for _ in range(runs):
        t0 = time.perf_counter(); result = fn(); t.append(time.perf_counter() - t0)
    return sorted(t)[runs // 2], result


def pair_pipeline(match=None):
    """(suspect drug, reaction) report counts, each report counted once per pair, as in sql/03_signals.sql."""
    return ([{"$match": match}] if match else []) + [
        {"$project": {"_id": 0,
                      "d": {"$setUnion": [{"$map": {"input": {"$filter": {"input": "$drugs", "cond": {"$and": [
                          {"$eq": ["$$this.role", 1]}, {"$ne": ["$$this.drug", None]}]}}}, "in": "$$this.drug"}}]},
                      "p": {"$setUnion": [{"$filter": {"input": "$reactions.pt", "cond": {"$ne": ["$$this", None]}}}]}}},
        {"$match": {"$expr": {"$lte": [{"$size": "$d"}, 5]}}},          # as the SQL screen: at most 5 suspect drugs
        {"$unwind": "$d"}, {"$unwind": "$p"},
        {"$group": {"_id": {"drug": "$d", "pt": "$p"}, "a": {"$sum": 1}}}]


def main():
    t0 = time.perf_counter()
    subprocess.run(L.PSQL + ["-d", "faers", "-f", str(HERE / "sql" / "03_signals.sql")], check=True)
    sql_signal_s = time.perf_counter() - t0
    col = pymongo.MongoClient(L.MONGO).faers.reports

    # profile of the data, from SQL
    p = rows("""SELECT (SELECT count(*) FROM report) AS reports,
                       (SELECT round(100.0 * avg(serious::int), 1) FROM report) AS pct_serious,
                       (SELECT round(100.0 * avg(('death' = ANY(outcomes))::int), 1) FROM report) AS pct_death,
                       (SELECT count(*) FROM report_drug WHERE role = 4) AS drug_rows_role4,
                       (SELECT round(100.0 * avg((name_source = 'openfda')::int), 1) FROM report_drug) AS pct_drug_rows_openfda_name,
                       (SELECT round(avg(n), 2) FROM (SELECT count(*) n FROM report_drug GROUP BY report_id) x) AS mean_drugs_per_report,
                       (SELECT max(n) FROM (SELECT count(*) n FROM report_drug GROUP BY report_id) x) AS max_drugs_per_report,
                       (SELECT round(avg(n), 2) FROM (SELECT count(*) n FROM report_reaction GROUP BY report_id) x) AS mean_reactions_per_report,
                       (SELECT count(DISTINCT drug) FROM report_drug WHERE role = 1) AS suspect_drugs,
                       (SELECT count(DISTINCT pt) FROM report_reaction) AS reaction_terms,
                       (SELECT count(*) FROM signal) AS pairs_with_3_reports,
                       (SELECT count(*) FILTER (WHERE is_signal) FROM signal) AS signals""")[0]
    p["reports_over_5_suspects"] = rows("SELECT count(*) AS n FROM (SELECT report_id FROM report_drug WHERE role = 1 AND drug IS NOT NULL GROUP BY 1 HAVING count(DISTINCT drug) > 5) x")[0]["n"]
    p["max_suspect_rows_in_one_report"] = rows("SELECT max(n) AS n FROM (SELECT count(*) n FROM report_drug WHERE role = 1 GROUP BY report_id) x")[0]["n"]
    (R / "profile.json").write_text(json.dumps(p, indent=2) + "\n")
    with open(R / "screen_sensitivity.csv", "w", newline="") as f:
        s = rows("SELECT * FROM screen_sensitivity")
        w = csv.DictWriter(f, fieldnames=s[0].keys()); w.writeheader(); w.writerows(s)

    L.psql(f"\\copy (SELECT * FROM signal ORDER BY drug, pt) TO '{R / 'signals.csv'}' WITH (FORMAT csv, HEADER)")
    known = []
    for drug, pt in KNOWN:
        r = rows(f"SELECT drug, pt, a, prr, ror, ror_lower95, chi2_yates, is_signal FROM signal WHERE drug = '{drug}' AND pt = '{pt}'")
        known.append(r[0] if r else {"drug": drug, "pt": pt, "a": 0, "prr": "", "ror": "", "ror_lower95": "", "chi2_yates": "", "is_signal": "f"})
    with open(R / "known_signals.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=known[0].keys()); w.writeheader(); w.writerows(known)

    top = rows("""SELECT drug, pt, a, prr, ror_lower95, chi2_yates FROM signal
                   WHERE is_signal AND drug IN ('SEMAGLUTIDE', 'TIRZEPATIDE', 'DUPILUMAB', 'ADALIMUMAB')
                   ORDER BY drug, a DESC""")
    top = [r for r in top if sum(1 for x in top if x["drug"] == r["drug"] and int(x["a"]) >= int(r["a"])) <= 6]
    with open(R / "signals_top.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=top[0].keys()); w.writeheader(); w.writerows(top)

    # the same pair counts from MongoDB, compared with PostgreSQL for every pair with 3 or more reports
    t_mongo_pairs, mongo_pairs = timed_mongo(lambda: {(d["_id"]["drug"], d["_id"]["pt"]): d["a"]
                                                      for d in col.aggregate(pair_pipeline(), allowDiskUse=True) if d["a"] >= 3}, runs=1)
    sql_pairs = {(r["drug"], r["pt"]): int(r["a"]) for r in rows("SELECT drug, pt, a FROM signal")}
    diff = sum(1 for k in sql_pairs.keys() | mongo_pairs.keys() if sql_pairs.get(k) != mongo_pairs.get(k))
    cmp_ = {"pairs_sql": len(sql_pairs), "pairs_mongo": len(mongo_pairs), "pairs_that_differ": diff,
            "sql_signal_seconds": round(sql_signal_s, 1), "mongo_pair_count_seconds": round(t_mongo_pairs, 1)}
    (R / "mongo_vs_sql.json").write_text(json.dumps(cmp_, indent=2) + "\n")

    # head-to-head on three everyday questions
    rid = rows("SELECT report_id FROM report_drug WHERE drug = 'SEMAGLUTIDE' AND role = 1 ORDER BY report_id LIMIT 1")[0]["report_id"]
    bench = []
    t, _ = timed_mongo(lambda: col.find_one({"_id": rid}))
    bench.append(("one full report by id", round(1000 * t, 2), round(1000 * timed_sql(f"""
        SELECT r.*, (SELECT json_agg(d) FROM report_drug d WHERE d.report_id = r.report_id),
                    (SELECT json_agg(x) FROM report_reaction x WHERE x.report_id = r.report_id)
          FROM report r WHERE r.report_id = '{rid}'"""), 2)))
    t, n_m = timed_mongo(lambda: col.count_documents({"drugs": {"$elemMatch": {"drug": "SEMAGLUTIDE", "role": 1}}, "reactions.pt": "PANCREATITIS"}))
    n_s = int(L.psql("""SELECT count(DISTINCT d.report_id) FROM report_drug d JOIN report_reaction x USING (report_id)
                         WHERE d.drug = 'SEMAGLUTIDE' AND d.role = 1 AND x.pt = 'PANCREATITIS'"""))
    assert n_m == n_s, (n_m, n_s)
    bench.append(("reports: suspect drug X with reaction Y", round(1000 * t, 2), round(1000 * timed_sql(
        """SELECT count(DISTINCT d.report_id) FROM report_drug d JOIN report_reaction x USING (report_id)
            WHERE d.drug = 'SEMAGLUTIDE' AND d.role = 1 AND x.pt = 'PANCREATITIS'"""), 2)))
    t, _ = timed_mongo(lambda: list(col.aggregate(pair_pipeline({"drugs": {"$elemMatch": {"drug": "SEMAGLUTIDE", "role": 1}}}))))
    bench.append(("all reaction counts for one drug", round(1000 * t, 2), round(1000 * timed_sql(
        """SELECT x.pt, count(DISTINCT d.report_id) FROM report_drug d JOIN report_reaction x USING (report_id)
            WHERE d.drug = 'SEMAGLUTIDE' AND d.role = 1 AND x.pt IS NOT NULL GROUP BY x.pt"""), 2)))
    bench.append(("count every drug-reaction pair", round(1000 * t_mongo_pairs, 0), round(1000 * timed_sql(
        """SELECT count(*) FROM (SELECT d.drug, x.pt, count(DISTINCT d.report_id) FROM report_drug d JOIN report_reaction x USING (report_id)
            WHERE d.role = 1 AND d.drug IS NOT NULL AND x.pt IS NOT NULL
              AND d.report_id IN (SELECT report_id FROM report_drug WHERE role = 1 AND drug IS NOT NULL GROUP BY 1 HAVING count(DISTINCT drug) <= 5)
            GROUP BY 1, 2) s""", runs=1), 0)))
    with open(R / "benchmark.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["question", "mongodb_ms", "postgresql_ms"]); w.writerows(bench)
    print(json.dumps(p, indent=2), json.dumps(cmp_, indent=2), *bench, sep="\n")
    print(open(R / "known_signals.csv").read())


if __name__ == "__main__":
    main()
