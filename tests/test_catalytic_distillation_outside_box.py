"""Checks of the catalytic column configurations outside the search box near the reference."""
import csv
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/catalytic_distillation_outside_box_20261102"
REFERENCE = 24895.552861


def test_configuration_list_is_reproduced():
    listed = subprocess.run([sys.executable, str(RESULTS / "scripts/list_configs.py")],
                            capture_output=True, text=True, check=True).stdout
    assert listed == (RESULTS / "configs.txt").read_text()
    assert len(listed.splitlines()) == 747


def test_no_accepted_configuration_beats_the_reference():
    rows = list(csv.DictReader((RESULTS / "results.csv").open()))
    configs = {tuple(map(int, line.split())) for line in (RESULTS / "configs.txt").read_text().splitlines()}
    assert {tuple(int(r[k]) for k in ["f1", "c1", "c2", "c3", "f2", "b"]) for r in rows} == configs
    accepted = [r for r in rows if r["modelstat"] in ("1", "2") and r["solvestat"] == "1"]
    assert len(accepted) == 255
    best = min(accepted, key=lambda r: float(r["zobj"]))
    assert float(best["zobj"]) > REFERENCE * (1 + 1e-5)
    assert [int(best[k]) for k in ["f1", "c1", "c2", "c3", "f2", "b"]] == [9, 9, 13, 17, 17, 21]
