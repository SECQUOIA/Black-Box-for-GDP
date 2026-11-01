"""Check the no-revisit D-SDA rerun on a few stored-response jobs; no solver calls."""

import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS = ["grid_easom_B100_seed5_dsda", "cstr_30_B43_seed4_dsda", "dynamic_B50_seed0_dsda"]


def load():
    spec = importlib.util.spec_from_file_location("dsda_no_revisit", ROOT / "experiments/dsda_no_revisit/run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rerun_never_repeats_and_legacy_mode_reproduces_published_runs(tmp_path):
    out = tmp_path / "run"
    assert load().main(["--cpu", "none", "--no-zip", "--output", str(out), "--jobs", *JOBS]) == 0
    checks = list(csv.DictReader(open(out / "checks.csv")))
    assert len(checks) == 7 and all(c["passed"] == "True" for c in checks)
    assert all(c["legacy_reproduces_published"] == "True" for c in checks if c["variant"] in ("grid", "single"))
    rows = {(r["case"], r["variant"]): r for r in csv.DictReader(open(out / "runs.csv"))}
    for r in rows.values():
        assert r["evaluations"] == r["distinct_evaluations"]
    # The published CSTR30 seed 4 run repeated 5 of its 26 evaluations and stopped at (5, 1).
    single = checks[[c["job_id"] for c in checks].index("cstr_30_B43_seed4_dsda")]
    assert single["published_repeats"] == "5"
    assert rows["cstr_30", "single"]["evaluations"] == "21"
    assert json.loads((out / "checks.json").read_text())["passed"]
