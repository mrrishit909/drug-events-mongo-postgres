"""Step 1: download one quarter of FDA adverse event reports (FAERS, via openFDA): 2026 Q2, 36 zipped JSON files.

    ./venv/bin/python download.py      -> data/raw/drug-event-00NN-of-0036.json.zip (not committed, 3.4 GB)
"""
import json
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw"
QUARTER = "2026 Q2"
CTX = ssl.create_default_context(cafile=certifi.where())


def partitions():
    index = json.loads(urllib.request.urlopen("https://api.fda.gov/download.json", context=CTX, timeout=120).read())
    parts = [p for p in index["results"]["drug"]["event"]["partitions"] if p["display_name"].startswith(QUARTER)]
    return index["results"]["drug"]["event"]["export_date"], parts


def fetch(p):
    out = RAW / p["file"].rsplit("/", 1)[1]
    if not out.exists():
        tmp = out.with_suffix(".part")
        with urllib.request.urlopen(p["file"], context=CTX, timeout=3600) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        tmp.rename(out)
    print(out.name, flush=True)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    export_date, parts = partitions()
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(fetch, parts))
    (HERE / "results").mkdir(exist_ok=True)
    meta = {"source": "openFDA drug/event download (FAERS)", "quarter": QUARTER, "export_date": export_date,
            "files": len(parts), "records_listed": sum(int(p["records"]) for p in parts)}
    (HERE / "results" / "pull.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(meta)


if __name__ == "__main__":
    main()
