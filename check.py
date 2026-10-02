"""The project's check: a third implementation, in plain Python from the slim documents, of what both databases computed.

    ./venv/bin/python check.py

1. Counts reconcile: documents = MongoDB documents = PostgreSQL reports, and drug and reaction rows add up.
2. The signal screen recomputes in Python from data/reports.ndjson: every pair's a, b, c, d, and PRR, ROR and
   chi-square, for all 113,416 screened pairs (results/signals.csv, written by PostgreSQL).
3. MongoDB's aggregation agreed with PostgreSQL on every pair count (results/mongo_vs_sql.json), and the screen
   flags the label reactions it should (results/known_signals.csv).
"""
import json
import math
from collections import Counter
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
R = HERE / "results"


def main():
    load = json.loads((R / "load.json").read_text())
    pairs, drug_n, pt_n, n = Counter(), Counter(), Counter(), 0
    docs = drug_rows = reaction_rows = 0
    for line in open(HERE / "data" / "reports.ndjson"):
        doc = json.loads(line)
        docs += 1
        drug_rows += len(doc["drugs"])
        reaction_rows += len(doc["reactions"])
        suspects = {d["drug"] for d in doc["drugs"] if d["role"] == 1 and d["drug"]}
        pts = {x["pt"] for x in doc["reactions"] if x["pt"]}
        if not suspects or not pts or len(suspects) > 5:
            continue
        n += 1
        drug_n.update(suspects)
        pt_n.update(pts)
        pairs.update((d, p) for d in suspects for p in pts)
    assert docs == load["mongodb"]["documents"] == load["postgresql"]["reports"]
    assert drug_rows == load["postgresql"]["drug_rows"] and reaction_rows == load["postgresql"]["reaction_rows"]

    s = pd.read_csv(R / "signals.csv", keep_default_na=False, na_values=[""])
    mine = {k: v for k, v in pairs.items() if v >= 3}
    assert len(mine) == len(s), (len(mine), len(s))
    for row in s.itertuples(index=False):
        a = mine[(row.drug, row.pt)]
        b, c = drug_n[row.drug] - a, pt_n[row.pt] - a
        d = n - a - b - c
        assert (a, b, c, d) == (row.a, row.b, row.c, row.d), row
        if c > 0 and b > 0:
            prr = (a / (a + b)) / (c / (c + d))
            ror = a * d / (b * c)
            chi2 = n * max(abs(a * d - b * c) - n / 2, 0) ** 2 / ((a + b) * (c + d) * (a + c) * (b + d))
            assert abs(prr - row.prr) < 1e-3 * max(1, prr) and abs(ror - row.ror) < 1e-3 * max(1, ror), row
            assert abs(chi2 - row.chi2_yates) < 0.01 * max(1, chi2), row
            assert (row.is_signal in ("t", True)) == (prr >= 2 and chi2 >= 4) or abs(prr - 2) < 1e-3 or abs(chi2 - 4) < 0.01, row

    cmp_ = json.loads((R / "mongo_vs_sql.json").read_text())
    assert cmp_["pairs_that_differ"] == 0 and cmp_["pairs_sql"] == cmp_["pairs_mongo"] == len(s)
    known = pd.read_csv(R / "known_signals.csv")
    found = int((known["is_signal"] == "t").sum())
    assert found >= 9, known
    print(f"OK: {docs:,} documents = MongoDB = PostgreSQL ({drug_rows:,} drug rows, {reaction_rows:,} reactions); "
          f"all {len(s):,} screened pairs recompute in Python (a, b, c, d, PRR, ROR, chi-square); MongoDB and PostgreSQL "
          f"agree on every pair; {found} of {len(known)} label reactions flagged")


if __name__ == "__main__":
    main()
