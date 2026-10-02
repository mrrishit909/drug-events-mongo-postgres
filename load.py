"""Step 3: load the same reports into MongoDB (as documents) and PostgreSQL (as three tables), then index both.

    ./run.sh start && ./venv/bin/python load.py     -> database faers in both; results/load.json (counts, sizes, times)
"""
import json
import subprocess
import time
from pathlib import Path

import pymongo

HERE = Path(__file__).parent
PSQL = [str(Path.home() / "micromamba/envs/analyst/bin/psql"), "-p", "5435", "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-qAt"]
MONGO = "mongodb://127.0.0.1:27018"


def psql(sql, db="faers"):
    return subprocess.run(PSQL + ["-d", db, "-c", sql], check=True, capture_output=True, text=True).stdout.strip()


def load_mongo():
    col = pymongo.MongoClient(MONGO).faers.reports
    col.drop()
    t0, batch = time.perf_counter(), []
    for line in open(HERE / "data" / "reports.ndjson"):
        batch.append(json.loads(line))
        if len(batch) == 10_000:
            col.insert_many(batch, ordered=False)
            batch = []
    if batch:
        col.insert_many(batch, ordered=False)
    load_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    col.create_index("drugs.drug")                    # multikey: one index entry per drug in the array
    col.create_index("reactions.pt")
    col.create_index("received")
    stats = pymongo.MongoClient(MONGO).faers.command("collstats", "reports")
    return {"documents": col.count_documents({}), "load_seconds": round(load_s, 1), "index_seconds": round(time.perf_counter() - t0, 1),
            "data_mb": round(stats["size"] / 1e6, 1), "storage_mb": round(stats["storageSize"] / 1e6, 1),
            "index_mb": round(stats["totalIndexSize"] / 1e6, 1)}


def load_postgres():
    if psql("SELECT 1 FROM pg_database WHERE datname = 'faers'", db="postgres") != "1":
        psql("CREATE DATABASE faers", db="postgres")
    subprocess.run(PSQL + ["-d", "faers", "-f", str(HERE / "sql" / "01_schema.sql")], check=True)
    t0 = time.perf_counter()
    for table in ["report", "report_drug", "report_reaction"]:
        psql(f"\\copy {table} FROM '{HERE / 'data' / 'pg' / (table + '.csv')}' WITH (FORMAT csv)")
    load_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    subprocess.run(PSQL + ["-d", "faers", "-f", str(HERE / "sql" / "02_indexes.sql")], check=True)
    index_s = time.perf_counter() - t0
    counts = psql("SELECT (SELECT count(*) FROM report) || ',' || (SELECT count(*) FROM report_drug) || ',' || (SELECT count(*) FROM report_reaction)")
    sizes = psql("SELECT round(sum(pg_table_size(c.oid)) / 1e6, 1) || ',' || round(sum(pg_indexes_size(c.oid)) / 1e6, 1) "
                 "FROM pg_class c WHERE relname IN ('report', 'report_drug', 'report_reaction')")
    r, d, x = map(int, counts.split(","))
    tmb, imb = map(float, sizes.split(","))
    return {"reports": r, "drug_rows": d, "reaction_rows": x, "load_seconds": round(load_s, 1), "index_seconds": round(index_s, 1),
            "table_mb": tmb, "index_mb": imb}


def main():
    out = {"mongodb": load_mongo(), "postgresql": load_postgres()}
    assert out["mongodb"]["documents"] == out["postgresql"]["reports"]
    (HERE / "results" / "load.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
