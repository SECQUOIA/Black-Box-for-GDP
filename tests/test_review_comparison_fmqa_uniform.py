"""Frozen-record paired analysis; no optimizer or solver executions."""

import copy
import json
from pathlib import Path
import random
import subprocess
import sys

import pytest

from review_comparison import fmqa_uniform as analysis
from review_comparison.common import csvrows, sha


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "results/review_comparison_20261020/tables/completed_runs.csv"
MANIFEST = INPUT.parent.parent / "manifest.json"


@pytest.fixture
def rows():
    return csvrows(INPUT)


def test_complete_pairing_is_order_independent_and_preserves_categories(rows):
    expected = analysis.pair_runs(rows)
    random.Random(123).shuffle(rows)
    assert analysis.pair_runs(rows) == expected
    assert len(expected) == 1190
    assert sum(p["scope"] == "grid" for p in expected) == 1050
    assert sum(p["scope"] == "process" for p in expected) == 140
    original = {
        (r["scope"], r["case"], int(r["budget"]), int(r["seed"]), r["method"]): r[
            "category"
        ]
        for r in rows
    }
    for pair in expected:
        key = tuple(pair[k] for k in ("scope", "case", "budget", "seed"))
        assert pair["fmqa_category"] == original[key + ("fmqa_sa",)]
        assert (
            pair["uniform_category"] == original[key + ("uniform_without_replacement",)]
        )


@pytest.mark.parametrize("both", [False, True])
def test_missing_method_or_entire_pair_is_rejected(rows, both):
    removed = {"fmqa_sa", "uniform_without_replacement"} if both else {"fmqa_sa"}
    rows = [
        r
        for r in rows
        if not (
            r["scope"] == "grid"
            and r["case"] == "ackley"
            and r["budget"] == "10"
            and r["seed"] == "0"
            and r["method"] in removed
        )
    ]
    with pytest.raises(ValueError, match="Missing .*pairing keys.*fmqa_sa"):
        analysis.pair_runs(rows)


def test_missing_entire_condition_is_rejected(rows):
    rows = [r for r in rows if not (r["case"] == "dynamic" and r["budget"] == "37")]
    with pytest.raises(ValueError, match="Missing 10 pairing keys"):
        analysis.pair_runs(rows)


def test_duplicate_pairing_is_rejected_including_equivalent_integer_keys(rows):
    duplicate = copy.copy(next(r for r in rows if r["method"] == "fmqa_sa"))
    duplicate["seed"] = "0" + duplicate["seed"]
    with pytest.raises(ValueError, match="Duplicate pairing key"):
        analysis.pair_runs(rows + [duplicate])


@pytest.mark.parametrize(
    "field,value",
    [
        ("case", "unknown_model"),
        ("budget", "11"),
        ("seed", "10"),
        ("seed", "0.5"),
        ("scope", "other"),
        ("category", "not_run"),
    ],
)
def test_condition_seed_or_incomplete_category_mismatch_is_rejected(rows, field, value):
    row = next(r for r in rows if r["method"] == "fmqa_sa")
    row[field] = value
    with pytest.raises(ValueError, match="Unexpected|Invalid|Incomplete"):
        analysis.pair_runs(rows)


def test_direction_four_joint_outcomes_and_failures_in_denominator(rows):
    categories = [
        ("target_reached", "target_reached"),
        ("target_reached", "execution_failed"),
        ("target_not_reached", "target_reached"),
        ("execution_failed", "target_not_reached"),
        ("target_reached", "target_not_reached"),
    ]
    for r in rows:
        if (
            r["case"] == "column"
            and int(r["seed"]) < 5
            and r["method"] in analysis.METHODS
        ):
            r["category"] = categories[int(r["seed"])][
                analysis.METHODS.index(r["method"])
            ]
    pairs = [
        p for p in analysis.pair_runs(rows) if p["case"] == "column" and p["seed"] < 5
    ]
    assert [p["success_difference"] for p in pairs] == [0, 1, -1, 0, 1]
    counts = analysis.outcome_counts(pairs)
    assert counts["pairs"] == 5
    assert [
        counts[k]
        for k in (
            "both_success",
            "fmqa_only_success",
            "uniform_only_success",
            "neither_success",
        )
    ] == [1, 2, 1, 1]
    assert counts["fmqa_success_rate"] == 3 / 5
    assert counts["uniform_success_rate"] == 2 / 5
    assert counts["mean_paired_success_difference"] == 1 / 5
    assert counts["fmqa_execution_failed"] == counts["uniform_execution_failed"] == 1
    assert pairs[1]["uniform_category"] == "execution_failed"


def test_grid_keeps_intact_function_vectors_and_process_conditions_separate(
    rows, monkeypatch
):
    pairs = analysis.pair_runs(rows)
    calls = []

    def capture(groups, **kwargs):
        calls.append((copy.deepcopy(groups), kwargs))
        return -0.5, 0.5

    monkeypatch.setattr(analysis, "paired_interval", capture)
    random.Random(84).shuffle(pairs)
    summaries = analysis.summarize_pairs(pairs)
    assert len(summaries) == len(calls) == 19
    for summary, (groups, kwargs) in zip(summaries, calls):
        grid = summary["scope"] == "grid"
        assert kwargs == {"seed": 20261020, "replications": 2000, "clustered": grid}
        assert len(groups) == (21 if grid else 1)
        assert all(len(vector) == 10 for vector in groups)
        cases = analysis.GRID_CASES if grid else [summary["case"]]
        for case, vector in zip(cases, groups):
            expected = sorted(
                (
                    p
                    for p in pairs
                    if p["scope"] == summary["scope"]
                    and p["case"] == case
                    and p["budget"] == summary["budget"]
                ),
                key=lambda p: p["seed"],
            )
            assert vector == [p["success_difference"] for p in expected]
        assert summary["pairs"] == (210 if grid else 10)
    assert [
        (r["case"], r["budget"]) for r in summaries if r["scope"] == "process"
    ] == list(analysis.PROCESS_CONDITIONS)
    assert len([r for r in summaries if r["case"] == "dynamic"]) == 6
    assert not any(r["scope"] == "process" and r["case"] == "all" for r in summaries)


def test_frozen_counts_crosscheck(rows):
    pairs = analysis.pair_runs(rows)
    for budget, expected in [
        (10, (16, 14)),
        (30, (47, 25)),
        (50, (76, 29)),
        (70, (102, 36)),
        (100, (129, 45)),
    ]:
        counts = analysis.outcome_counts(
            [p for p in pairs if p["scope"] == "grid" and p["budget"] == budget]
        )
        assert counts["pairs"] == 210
        assert (
            counts["fmqa_target_reached"],
            counts["uniform_target_reached"],
        ) == expected
    total = analysis.outcome_counts([p for p in pairs if p["scope"] == "process"])
    assert (
        total["pairs"],
        total["fmqa_target_reached"],
        total["uniform_target_reached"],
    ) == (140, 42, 36)


def test_input_digest_and_frozen_source_checked_before_outputs(tmp_path, monkeypatch):
    changed = tmp_path / "changed.csv"
    changed.write_bytes(INPUT.read_bytes() + b"\n")
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="Input SHA256 mismatch"):
        analysis.run(changed, output, MANIFEST)
    assert not output.exists()
    original_sha = analysis.sha
    monkeypatch.setattr(
        analysis,
        "sha",
        lambda p: "changed" if Path(p).name == "analysis.py" else original_sha(p),
    )
    with pytest.raises(ValueError, match="Frozen analysis source differs"):
        analysis.run(INPUT, output, MANIFEST)
    assert not output.exists()


def test_cli_repeat_csv_bytes_hashes_and_no_overwrite(tmp_path):
    outputs = [tmp_path / "first", tmp_path / "second"]
    for output in outputs:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "review_comparison.fmqa_uniform",
                "--input",
                str(INPUT),
                "--manifest",
                str(MANIFEST),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    for name in ("paired_runs.csv", "paired_success.csv", "README.md"):
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()
        assert (outputs[0] / name).read_bytes() == (INPUT.parent.parent / "fmqa_uniform" / name).read_bytes()
    assert len(csvrows(outputs[0] / "paired_success.csv")) == 19
    manifest = json.loads((outputs[0] / "manifest.json").read_text())
    assert manifest["input"]["sha256"] == sha(INPUT)
    assert (
        manifest["execution_provider_revision"]
        == json.loads(MANIFEST.read_text())["execution_provider_revision"]
    )
    for name, digest in manifest["outputs_sha256"].items():
        assert sha(outputs[0] / name) == digest
    for name, digest in manifest["analysis_sources_sha256"].items():
        assert sha(ROOT / name) == digest
    before = sha(outputs[0] / "manifest.json")
    with pytest.raises(FileExistsError):
        analysis.run(INPUT, outputs[0], MANIFEST)
    assert sha(outputs[0] / "manifest.json") == before


def test_current_cstr15_status_matches_retained_evidence():
    directory = ROOT / "results/review_feasibility_tautology_20261020"
    summary = json.loads((directory / "summary.json").read_text())
    residuals = json.loads((directory / "residuals.json").read_text())
    assessment = summary["assessment"]
    assert summary["returned_solution"] and summary["tightened_feasibility_passed"]
    assert summary["bound_discrepancy_persists"]
    for key in ("objective", "maximum_unscaled_primal_violation"):
        assert assessment[key] == residuals[key]
    assert residuals["maximum_unscaled_primal_violation"] <= residuals["tolerance"] == 1e-8
    assert assessment["bound_minus_witness"] == assessment["reported_gloa_lower_bound"] - assessment["objective"]
    assert assessment["bound_minus_witness"] > assessment["audit_tolerance"]
    for name in (
        "docs/review_comparison_status.md",
        "manuscript/README.md",
        "results/review_comparison_20261020/README.md",
        "results/review_comparison_20261020/fmqa_uniform/README.md",
    ):
        text = (ROOT / name).read_text()
        for key in ("objective", "maximum_unscaled_primal_violation", "bound_minus_witness"):
            assert str(assessment[key]) in text, (name, key)
        assert "854a1a7fc5a20a5489d82ef7991a16aaf89025f3" in text
        assert "not a proof of exact mathematical feasibility, global optimality or a solver defect" in text
        assert "review_feasibility_tautology_20261020/" in text
    historical = json.loads((ROOT / "results/review_diagnostics_20261020/feasibility/interpretation.json").read_text())
    earlier = json.loads((ROOT / "results/review_feasibility_followup_20261020/summary.json").read_text())
    assert historical["status"] == "tightened_feasibility_incomplete"
    assert historical["returned_new_solutions"] == 0
    assert earlier["returned_solutions"] == 0
    assert earlier["tightened_feasibility_passed"] is False
    assert earlier["bound_discrepancy_persists"] is None


def test_status_correction_preserves_original_manifests_and_evidence():
    correction = json.loads((INPUT.parent.parent / "status_correction.json").read_text())
    for name, digest in correction["preserved_files_sha256"].items():
        assert sha(ROOT / name) == digest, name
    for name, record in correction["updated_files"].items():
        # These two living documents were subsequently updated with the authorized
        # Overleaf revision; retain the exact status-correction publication bytes.
        if name in {"docs/review_comparison_status.md", "manuscript/README.md"}:
            path = ROOT / "manuscript/review_history/cstr_status_correction" / name
        else:
            path = ROOT / name
        assert sha(path) == record["current_sha256"], name
