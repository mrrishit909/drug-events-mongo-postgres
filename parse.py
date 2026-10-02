"""Step 2: slim each report once, then feed both databases from that one file.

    ./venv/bin/python parse.py     -> data/reports.ndjson (one slim JSON document per report, for MongoDB)
                                      data/pg/report.csv, report_drug.csv, report_reaction.csv (for PostgreSQL COPY)

Kept: dates, seriousness, reporter, patient age/sex/weight, every drug (role, names) and every reaction (MedDRA term).
Dropped: the free-text case narrative and dosage text (privacy, and not needed). A drug is identified by FDA's
harmonised generic name when openFDA matched it, else by the reported active substance, else by the product name.
"""
import csv
import json
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import ijson

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw"
OUT = HERE / "data"
YEARS = {"800": 10, "801": 1, "802": 1 / 12, "803": 1 / 52, "804": 1 / 365.25, "805": 1 / 8766}   # age unit -> years
FLAGS = ["death", "lifethreatening", "hospitalization", "disabling", "congenitalanomali", "other"]


def norm(s):
    return " ".join(str(s).upper().replace(".", " ").split()) if s else None


def slim(r):
    p = r.get("patient", {})
    age, unit = p.get("patientonsetage"), p.get("patientonsetageunit")
    try:
        age_years = round(float(age) * YEARS[unit], 2) if age and unit in YEARS else None
    except ValueError:
        age_years = None
    drugs = []
    for d in p.get("drug", []):
        of = d.get("openfda", {})
        generic = norm((of.get("generic_name") or [None])[0])
        substance = norm((d.get("activesubstance") or {}).get("activesubstancename"))
        product = norm(d.get("medicinalproduct"))
        drugs.append({"role": int(d["drugcharacterization"]) if str(d.get("drugcharacterization", "")).isdigit() else None,
                      "drug": generic or substance or product,
                      "name_source": "openfda" if generic else "substance" if substance else "product" if product else None,
                      "product": product, "indication": norm(d.get("drugindication")),
                      "pharm_class": (of.get("pharm_class_epc") or [None])[0]})
    reactions = [{"pt": norm(x.get("reactionmeddrapt")), "outcome": x.get("reactionoutcome")} for x in p.get("reaction", [])]
    rd = r.get("receivedate")
    return {"_id": r["safetyreportid"], "version": r.get("safetyreportversion"),
            "received": f"{rd[:4]}-{rd[4:6]}-{rd[6:8]}" if rd else None,
            "country": r.get("occurcountry") or r.get("primarysourcecountry"),
            "reporter": (r.get("primarysource") or {}).get("qualification"),
            "serious": r.get("serious") == "1", "outcomes": [f for f in FLAGS if r.get("seriousness" + f) == "1"],
            "duplicate_of_other_source": r.get("duplicate") == "1",
            "patient": {"age_years": age_years, "sex": {"1": "M", "2": "F"}.get(p.get("patientsex")),
                        "weight_kg": float(p["patientweight"]) if str(p.get("patientweight", "")).replace(".", "", 1).isdigit() else None},
            "drugs": drugs, "reactions": reactions}


def one_file(path):
    docs = []
    with zipfile.ZipFile(path) as z, z.open(z.infolist()[0]) as f:
        for r in ijson.items(f, "results.item", use_float=True):
            docs.append(slim(r))
    part = OUT / "parts" / (path.stem + ".ndjson")
    part.parent.mkdir(parents=True, exist_ok=True)
    with open(part, "w") as out:
        for doc in docs:
            out.write(json.dumps(doc) + "\n")
    return path.name, len(docs)


def main():
    files = sorted(RAW.glob("drug-event-*.json.zip"))
    assert len(files) == json.loads((HERE / "results" / "pull.json").read_text())["files"]
    with ProcessPoolExecutor(6) as pool:
        for name, n in pool.map(one_file, files):
            print(name, n, flush=True)
    # one MongoDB file and three PostgreSQL tables from the same documents. Pass 1 picks, for a report id seen more
    # than once, its highest version; pass 2 writes only those lines.
    parts = sorted((OUT / "parts").glob("*.ndjson"))
    best = {}
    for pi, part in enumerate(parts):
        for li, line in enumerate(open(part)):
            doc = json.loads(line)
            v = int(doc["version"] or 0)
            if doc["_id"] not in best or v >= best[doc["_id"]][0]:
                best[doc["_id"]] = (v, pi, li)
    keep = {(pi, li) for _, pi, li in best.values()}
    (OUT / "pg").mkdir(exist_ok=True)
    with open(OUT / "reports.ndjson", "w") as nd, open(OUT / "pg" / "report.csv", "w", newline="") as fr, \
            open(OUT / "pg" / "report_drug.csv", "w", newline="") as fd, open(OUT / "pg" / "report_reaction.csv", "w", newline="") as fx:
        wr, wd, wx = csv.writer(fr), csv.writer(fd), csv.writer(fx)
        for pi, part in enumerate(parts):
            for li, line in enumerate(open(part)):
                if (pi, li) not in keep:
                    continue
                doc = json.loads(line)
                nd.write(line)
                p = doc["patient"]
                wr.writerow([doc["_id"], doc["version"], doc["received"], doc["country"], doc["reporter"], doc["serious"],
                             "{" + ",".join(doc["outcomes"]) + "}", doc["duplicate_of_other_source"], p["age_years"], p["sex"], p["weight_kg"]])
                for i, d in enumerate(doc["drugs"], 1):
                    wd.writerow([doc["_id"], i, d["role"], d["drug"], d["name_source"], d["product"], d["indication"], d["pharm_class"]])
                for i, x in enumerate(doc["reactions"], 1):
                    wx.writerow([doc["_id"], i, x["pt"], x["outcome"]])
    lines = sum(1 for part in parts for _ in open(part))
    (HERE / "results" / "parse.json").write_text(json.dumps({"reports_in_files": lines, "unique_reports": len(best),
                                                            "older_versions_dropped": lines - len(best)}, indent=2) + "\n")
    print(len(best), "unique reports of", lines)


if __name__ == "__main__":
    main()
