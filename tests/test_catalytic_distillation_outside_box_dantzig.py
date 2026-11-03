"""Checks of the Dantzig rerun of the catalytic column configurations outside the search box."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/catalytic_distillation_outside_box_dantzig_20261103"
WORKSTATION = ROOT / "results/catalytic_distillation_outside_box_20261102"
BEST_KNOWN = json.loads((ROOT / "results/catalytic_distillation_live_20261101/best_known.json").read_text())
STAGES = ["f1", "c1", "c2", "c3", "f2", "b"]


def rows(path):
    return list(csv.DictReader((path / "results.csv").open()))


def test_same_configurations_as_the_workstation_run():
    assert (RESULTS / "configs.txt").read_text() == (WORKSTATION / "configs.txt").read_text()
    configs = [tuple(map(int, line.split())) for line in (RESULTS / "configs.txt").read_text().splitlines()]
    assert sorted(tuple(int(r[k]) for k in STAGES) for r in rows(RESULTS)) == sorted(configs)
    assert len(configs) == 747


def test_results_match_the_archive_and_the_release():
    archive = RESULTS / "evidence/outside_box_results.zip"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert (RESULTS / "evidence/outside_box_results.zip.sha256").read_text().split()[0] == digest
    with zipfile.ZipFile(archive) as z:
        for r in rows(RESULTS):
            line = z.read("runs/" + "_".join(r[k] for k in STAGES) + "/result.txt").decode()
            fields = dict(item.split("=", 1) for item in line.split() if "=" in item)
            assert (fields["modelstat"], fields["solvestat"], fields["zobj"]) == (r["modelstat"], r["solvestat"], r["zobj"])
    assert "54.3.1" in (RESULTS / "run.log").read_text()


def test_no_accepted_configuration_beats_the_reference():
    table = rows(RESULTS)
    assert Counter((r["modelstat"], r["solvestat"]) for r in table) == {("2", "1"): 255, ("5", "1"): 492}
    assert max(float(r["resusd"]) for r in table) < 300
    reference = BEST_KNOWN["objective"]
    accepted = [r for r in table if r["modelstat"] in ("1", "2") and r["solvestat"] == "1"]
    best = min(accepted, key=lambda r: float(r["zobj"]))
    assert float(best["zobj"]) > reference * (1 + 1e-5)
    assert [int(best[k]) for k in STAGES] == [9, 9, 13, 17, 17, 21]
    assert round(100 * (float(best["zobj"]) - reference) / reference, 2) == 0.14


def test_rerun_reproduces_the_workstation_outcomes():
    old = {tuple(r[k] for k in STAGES): r for r in rows(WORKSTATION)}
    for r in rows(RESULTS):
        o = old[tuple(r[k] for k in STAGES)]
        assert (r["modelstat"], r["solvestat"]) == (o["modelstat"], o["solvestat"])
        if r["modelstat"] in ("1", "2") and r["solvestat"] == "1":
            assert r["zobj"] == o["zobj"]
