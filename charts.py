"""Step 7: charts.

    ./venv/bin/python charts.py   -> charts/01_models.png (Graphviz), 02_storage.png, 03_benchmark.png, 04_screen.png, 05_known.png
"""
import json
import shutil
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
R = HERE / "results"
INK, DIM, GRID, BG, BLUE, ORANGE, GRAY = "#f2f2f0", "#8a8a87", "#1d1d1d", "#0b0b0b", "#3987e5", "#d95926", "#9a9a96"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": INK,
    "axes.edgecolor": "#3a3a3a", "axes.labelcolor": DIM, "xtick.color": DIM, "ytick.color": DIM,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 1,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"], "font.size": 11, "axes.titlesize": 13,
    "axes.titlelocation": "left", "axes.titlepad": 12,
})
DOT = shutil.which("dot") or str(Path.home() / "micromamba" / "envs" / "analyst" / "bin" / "dot")


def save(fig, name):
    fig.tight_layout()
    fig.savefig(HERE / "charts" / name, dpi=150)
    plt.close(fig)


def models():
    cell = lambda t, c="#141414": f'<tr><td align="left" bgcolor="{c}">{t}</td></tr>'
    head = lambda t, c: f'<tr><td bgcolor="{c}"><b>{t}</b></td></tr>'
    doc = ('<table border="1" cellborder="0" cellspacing="0" cellpadding="4" color="#3a3a3a" bgcolor="#141414">'
           + head("MongoDB: one document per report", "#1f3b5c")
           + cell("_id, received, serious, outcomes[ ]") + cell("patient { age, sex, weight }")
           + cell("drugs [ { role, drug, product, indication } ... ]") + cell("reactions [ { pt, outcome } ... ]") + "</table>")
    tab = lambda name, rows: ('<table border="1" cellborder="0" cellspacing="0" cellpadding="4" color="#3a3a3a" bgcolor="#141414">'
                              + head(name, "#4a2414") + "".join(cell(r) for r in rows) + "</table>")
    lines = ['digraph M {', '  graph [bgcolor="#0b0b0b", rankdir=LR, nodesep=0.3, ranksep=0.9];',
             '  node [shape=plaintext, fontname="Helvetica", fontcolor="#f2f2f0", fontsize=12];',
             '  edge [color="#8a8a87", fontname="Helvetica", fontsize=10, fontcolor="#8a8a87"];',
             f'  doc [label=<{doc}>];',
             f'  report [label=<{tab("PostgreSQL: report", ["report_id (PK)", "received, serious, outcomes", "age, sex, weight"])}>];',
             f'  drug [label=<{tab("report_drug", ["report_id, seq (PK)", "role, drug, product", "indication, pharm_class"])}>];',
             f'  reaction [label=<{tab("report_reaction", ["report_id, seq (PK)", "pt, outcome"])}>];',
             '  doc -> report [label="same 422,456 reports", style=dashed];',
             '  report -> drug [label="1 : 4.5 on average", arrowhead=crow];', '  report -> reaction [label="1 : 3.3", arrowhead=crow];', '}']
    (HERE / "charts" / "models.dot").write_text("\n".join(lines) + "\n")
    subprocess.run([DOT, "-Tpng", "-Gdpi=130", str(HERE / "charts" / "models.dot"), "-o", str(HERE / "charts" / "01_models.png")], check=True)


def main():
    (HERE / "charts").mkdir(exist_ok=True)
    models()

    ld = json.loads((R / "load.json").read_text())
    m, p = ld["mongodb"], ld["postgresql"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.4))
    axes[0].barh(["MongoDB", "PostgreSQL"], [m["storage_mb"], p["table_mb"]], color=[BLUE, ORANGE], height=0.5, label="data")
    axes[0].barh(["MongoDB", "PostgreSQL"], [m["index_mb"], p["index_mb"]], left=[m["storage_mb"], p["table_mb"]], color=GRAY, height=0.5, label="indexes")
    for i, (a, b) in enumerate([(m["storage_mb"], m["index_mb"]), (p["table_mb"], p["index_mb"])]):
        axes[0].text(a + b + 10, i, f"{a:.0f} + {b:.0f} MB", va="center", color=INK, fontsize=9)
    axes[0].set_xlim(0, 820); axes[0].legend(frameon=False, labelcolor=INK, fontsize=9, loc="lower right")
    axes[0].grid(axis="y", visible=False)
    axes[0].set_title("On disk (MongoDB compresses documents)", fontsize=12)
    axes[1].barh(["MongoDB", "PostgreSQL"], [m["load_seconds"], p["load_seconds"]], color=[BLUE, ORANGE], height=0.5)
    axes[1].barh(["MongoDB", "PostgreSQL"], [m["index_seconds"], p["index_seconds"]], left=[m["load_seconds"], p["load_seconds"]], color=GRAY, height=0.5)
    for i, (a, b) in enumerate([(m["load_seconds"], m["index_seconds"]), (p["load_seconds"], p["index_seconds"])]):
        axes[1].text(a + b + 0.6, i, f"{a:.1f} s load + {b:.1f} s index", va="center", color=INK, fontsize=9)
    axes[1].set_xlim(0, 52); axes[1].grid(axis="y", visible=False)
    axes[1].set_title("Load and index time", fontsize=12)
    fig.suptitle("The same 422,456 reports in each database", x=0.01, ha="left", fontsize=13, color=INK)
    save(fig, "02_storage.png")

    b = pd.read_csv(R / "benchmark.csv")
    fig, ax = plt.subplots(figsize=(11, 3.8))
    y = np.arange(len(b))
    ax.barh(y + 0.19, b["mongodb_ms"], height=0.38, color=BLUE, label="MongoDB")
    ax.barh(y - 0.19, b["postgresql_ms"], height=0.38, color=ORANGE, label="PostgreSQL")
    for i, r in b.iterrows():
        ax.text(r["mongodb_ms"] * 1.15, i + 0.19, f"{r['mongodb_ms']:g} ms", va="center", color=INK, fontsize=8.5)
        ax.text(r["postgresql_ms"] * 1.15, i - 0.19, f"{r['postgresql_ms']:g} ms", va="center", color=INK, fontsize=8.5)
    ax.set_yticks(y, b["question"]); ax.invert_yaxis(); ax.set_xscale("log"); ax.set_xlim(0.1, 60000)
    ax.legend(frameon=False, labelcolor=INK, fontsize=9, loc="upper right"); ax.grid(axis="y", visible=False)
    ax.set_xlabel("milliseconds (log scale): median of 3 runs, the full count 1 run; PostgreSQL timed by psql's \\timing in one session")
    ax.set_title("Same questions, same indexes: a tie on lookups; documents win when whole reports are needed")
    save(fig, "03_benchmark.png")

    s = pd.read_csv(R / "screen_sensitivity.csv").set_index("screen")
    allr, small = s.loc["all reports"], s.loc["reports with at most 5 suspect drugs"]
    fig, ax = plt.subplots(figsize=(10, 3.4))
    labels = ["reports", "pairs screened (3+ reports)", "pairs flagged"]
    x = np.arange(3)
    ax.bar(x - 0.19, [allr["reports"], allr["pairs_with_3_reports"], allr["signals"]], width=0.38, color=GRAY, label="all reports")
    ax.bar(x + 0.19, [small["reports"], small["pairs_with_3_reports"], small["signals"]], width=0.38, color=BLUE,
           label="without the 2.2% naming more than 5 suspect drugs")
    for i, (u, v) in enumerate(zip([allr["reports"], allr["pairs_with_3_reports"], allr["signals"]],
                                   [small["reports"], small["pairs_with_3_reports"], small["signals"]])):
        ax.text(i - 0.19, u + 6000, f"{u:,}", ha="center", color=INK, fontsize=9)
        ax.text(i + 0.19, v + 6000, f"{v:,}", ha="center", color=INK, fontsize=9)
    ax.set_xticks(x, labels); ax.set_ylim(0, 480000); ax.legend(frameon=False, labelcolor=INK, fontsize=9, loc="upper right")
    ax.grid(axis="x", visible=False); ax.yaxis.set_major_formatter(lambda v, _: f"{v / 1000:.0f}k")
    ax.set_title("A few huge reports drown the screen: 2.2% of reports made 65% of the flags")
    save(fig, "04_screen.png")

    k = pd.read_csv(R / "known_signals.csv").iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    names = [f"{d.title()}: {p.capitalize()}" for d, p in zip(k["drug"], k["pt"])]
    names = [n.replace("International normalised ratio increased", "INR increased") for n in names]
    y = np.arange(len(k))
    col = [BLUE if s == "t" else ORANGE for s in k["is_signal"]]
    ax.errorbar(k["ror"], y, xerr=[k["ror"] - k["ror_lower95"], np.zeros(len(k))], fmt="none", ecolor=DIM, elinewidth=1)
    ax.scatter(k["ror"], y, color=col, s=45, zorder=3)
    for i, (r, a) in enumerate(zip(k["ror"], k["a"])):
        ax.text(r * 1.25, i, f"ROR {r:,.1f} · {a} reports" if r < 100 else f"ROR {r:,.0f} · {a} reports", va="center", color=INK, fontsize=8.5)
    ax.axvline(1, color=DIM, linestyle="--", linewidth=1)
    ax.set_yticks(y, names); ax.set_xscale("log"); ax.set_xlim(0.3, 20000); ax.grid(axis="y", visible=False)
    ax.set_xlabel("reporting odds ratio with its lower 95% bound (log scale); blue = flagged, orange = missed")
    ax.set_title("Reactions already on these drugs' labels: the screen finds 9 of 10")
    save(fig, "05_known.png")
    print("charts written")


if __name__ == "__main__":
    main()
