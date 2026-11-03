"""Checks of the catalytic column configurations outside the search box near the reference."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/catalytic_distillation_outside_box_20261102"
BEST_KNOWN = json.loads((ROOT / "results/catalytic_distillation_live_20261101/best_known.json").read_text())
STAGES = ["f1", "c1", "c2", "c3", "f2", "b"]


def rows():
    return list(csv.DictReader((RESULTS / "results.csv").open()))


def test_configuration_list_is_reproduced():
    listed = subprocess.run([sys.executable, str(RESULTS / "scripts/list_configs.py")],
                            capture_output=True, text=True, check=True).stdout
    assert listed == (RESULTS / "configs.txt").read_text()
    assert len(listed.splitlines()) == 747


def test_results_cover_every_configuration_once_and_match_the_archive():
    table = rows()
    configs = [tuple(map(int, line.split())) for line in (RESULTS / "configs.txt").read_text().splitlines()]
    assert len(table) == len(configs) == 747
    assert sorted(tuple(int(r[k]) for k in STAGES) for r in table) == sorted(configs)
    archive = RESULTS / "evidence/outside_box_results.zip"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert (RESULTS / "evidence/outside_box_results.zip.sha256").read_text().split()[0] == digest
    with zipfile.ZipFile(archive) as z:
        for r in table:
            name = "runs/" + "_".join(r[k] for k in STAGES) + "/result.txt"
            line = z.read(name).decode()
            fields = dict(item.split("=", 1) for item in line.split() if "=" in item)
            assert (fields["modelstat"], fields["solvestat"], fields["zobj"]) == (r["modelstat"], r["solvestat"], r["zobj"])


def test_no_accepted_configuration_beats_the_reference():
    table = rows()
    assert Counter((r["modelstat"], r["solvestat"]) for r in table) == {("2", "1"): 255, ("5", "1"): 492}
    assert max(float(r["resusd"]) for r in table) < 300
    reference = BEST_KNOWN["objective"]
    assert BEST_KNOWN["positions"] == [8, 8, 12, 17, 17, 21]
    accepted = [r for r in table if r["modelstat"] in ("1", "2") and r["solvestat"] == "1"]
    best = min(accepted, key=lambda r: float(r["zobj"]))
    assert float(best["zobj"]) > reference * (1 + 1e-5)
    assert [int(best[k]) for k in STAGES] == [9, 9, 13, 17, 17, 21]
    assert round(100 * (float(best["zobj"]) - reference) / reference, 2) == 0.14
