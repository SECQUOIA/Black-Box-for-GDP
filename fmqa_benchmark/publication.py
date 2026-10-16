"""The current FMQA-SA dataset is the pinned QHD_Data PyTorch run."""

import csv
import math
from pathlib import Path

from overnight_benchmark.common import read, sha

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "results/fmqa_qhd_20261012"
DISPLAY_LABEL = "FMQA-SA"
LEGACY_LABEL = "FMQA-SA (NumPy legacy)"
BACKEND = "pytorch_qhd_data"
ARCHIVE_NAME = "fmqa_qhd_20261012_034123_8kcczd4b.zip"


def process_runs():
    audit = read(CURRENT / "audit.json")
    if audit["backend"] != BACKEND or sha(ROOT / audit["archive"]) != audit["archive_sha256"]:
        raise ValueError("Current FMQA archive identity mismatch")
    sources = {audit["archive"]: audit["archive_sha256"]}
    for name in ("process_runs.csv", "run.json", "publication_evaluation_costs.csv.gz", "missing_unique_points.csv"):
        if sha(CURRENT / name) != audit["files_sha256"][name]:
            raise ValueError(f"Current FMQA checksum mismatch: {name}")
        sources[str((CURRENT / name).relative_to(ROOT))] = audit["files_sha256"][name]
    sources[str((CURRENT / "audit.json").relative_to(ROOT))] = sha(CURRENT / "audit.json")
    with (CURRENT / "process_runs.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    numeric = ("recorded_dfo_s", "recorded_lookup_s", "search_overhead_s", "accepted_nlp_s",
               "unaccepted_nlp_s", "dynamic_preparation_s", "estimated_total_s", "recorded_best_value", "target_value")
    for row in rows:
        for key in numeric:
            row[key] = float(row[key]) if row[key] else math.nan
        for key in ("budget", "seed", "missing_point_costs"):
            row[key] = int(row[key])
        for key in ("lookup_target_hit", "cost_complete"):
            row[key] = row[key] == "True"
        if row["backend"] != BACKEND or math.isfinite(row["estimated_total_s"]) != row["cost_complete"]:
            raise ValueError("Incorrect FMQA backend or missing-time treatment")
    if len(rows) != 140 or len({r["job_id"] for r in rows}) != 140:
        raise ValueError("Expected 140 distinct current FMQA process runs")
    return rows, sources
