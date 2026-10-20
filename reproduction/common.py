"""Small solver-free I/O helpers for the frozen manuscript companion."""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "reproduction/data"
GRID = ROOT / "results/grid_gdp_dfo_20261011"
PROCESS = ROOT / "results/process_ipopt_bam_v2_20261015/tables"
METHODS = ("dsda", "rbfopt", "bam", "fmqa_sa")


def read_json(path):
    return json.loads(Path(path).read_text())


def rows(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def write_table(path, records):
    """CSV and readable Markdown; retain full precision, no manuscript prose."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for row in records for k in row))

    def cell(value):
        return json.dumps(value) if isinstance(value, (list, dict)) else value

    converted = [{k: cell(r.get(k, "")) for k in keys} for r in records]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, keys, lineterminator="\n")
        writer.writeheader()
        writer.writerows(converted)
    lines = [
        "| " + " | ".join(keys) + " |",
        "| " + " | ".join("---" for _ in keys) + " |",
    ]
    lines.extend(
        "| "
        + " | ".join(str(r[k]).replace("|", "\\|").replace("\n", " ") for k in keys)
        + " |"
        for r in converted
    )
    path.with_suffix(".md").write_text("\n".join(lines) + "\n")
