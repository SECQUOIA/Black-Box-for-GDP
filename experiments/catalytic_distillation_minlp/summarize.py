"""Collect the solver runs of run_solvers.sh into one table.

  python experiments/catalytic_distillation_minlp/summarize.py RESULTS

Reads RESULTS/<form>/<solver>/result.txt and wall.txt for the forms product, bigm, and chull
and writes RESULTS/summary.csv with the GAMS model and solver status, objective, returned
configuration, and wall time of every run.
"""

import csv
from pathlib import Path
import sys

FORMS = ["product", "bigm", "chull"]
SOLVERS = ["dicopt", "sbb", "baron", "scip"]
FIELDS = ["modelstat", "solvestat", "zobj", "f1", "c1", "c2", "c3", "f2", "b", "maxfrac"]


def fields(path):
    return dict(item.split("=", 1) for item in path.read_text().split() if "=" in item)


def summarize(results):
    results = Path(results)
    rows = []
    for form in FORMS:
        for solver in SOLVERS:
            run = results / form / solver
            if not (run / "result.txt").exists():
                continue
            values = fields(run / "result.txt")
            row = {"form": form, "solver": solver, **{key: values.get(key, "") for key in FIELDS}}
            row["wall_s"] = f"{float(fields(run / 'wall.txt')['wall_s']):.1f}"
            rows.append(row)
    with (results / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["form", "solver", *FIELDS, "wall_s"])
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    for row in summarize(sys.argv[1]):
        print(row)
