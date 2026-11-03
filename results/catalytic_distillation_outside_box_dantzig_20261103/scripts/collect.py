"""Collect the result lines of the Dantzig outside-box check and compare them with the workstation run.

  python collect.py RUNS_DIR OUT_DIR WORKSTATION_RESULTS_CSV

RUNS_DIR holds runs/<f1>_<c1>_<c2>_<c3>_<f2>_<b>/result.txt as written by solve_one.sh.
Writes results.csv (same columns as the workstation run), comparison.csv, and
evidence/outside_box_results.zip with its SHA-256.
"""
import csv
import hashlib
from pathlib import Path
import sys
import zipfile

STAGES = ["f1", "c1", "c2", "c3", "f2", "b"]
COLUMNS = STAGES + ["solver", "modelstat", "solvestat", "zobj", "resusd", "xETBE"]


def accepted(row):
    return row["modelstat"] in ("1", "2") and row["solvestat"] == "1"


def parse(line):
    return dict(item.split("=", 1) for item in line.split() if "=" in item)


def main(runs, out, workstation):
    runs, out = Path(runs), Path(out)
    configs = [tuple(line.split()) for line in (out / "configs.txt").read_text().splitlines()]
    rows = []
    for config in configs:
        fields = parse((runs / "_".join(config) / "result.txt").read_text())
        rows.append({k: fields[k] for k in COLUMNS})
    with open(out / "results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (out / "evidence").mkdir(exist_ok=True)
    archive = out / "evidence/outside_box_results.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for config in configs:
            name = "runs/" + "_".join(config) + "/result.txt"
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 3, 0, 0, 0))
            z.writestr(info, (runs / "_".join(config) / "result.txt").read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out / "evidence/outside_box_results.zip.sha256").write_text(f"{digest}  outside_box_results.zip\n")
    old = {tuple(r[k] for k in STAGES): r for r in csv.DictReader(open(workstation))}
    comparison = []
    for r in rows:
        o = old[tuple(r[k] for k in STAGES)]
        comparison.append(dict(**{k: r[k] for k in STAGES},
                               status_dantzig=f"{r['modelstat']}/{r['solvestat']}",
                               status_workstation=f"{o['modelstat']}/{o['solvestat']}",
                               accepted_dantzig=accepted(r), accepted_workstation=accepted(o),
                               zobj_dantzig=r["zobj"], zobj_workstation=o["zobj"],
                               abs_diff=abs(float(r["zobj"]) - float(o["zobj"]))))
    with open(out / "comparison.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(comparison[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(comparison)


if __name__ == "__main__":
    main(*sys.argv[1:])
