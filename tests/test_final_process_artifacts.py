"""Final comparison can be reconstructed without process or DFO solvers."""

import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import verify_final_process as verifier


def test_final_process_sources_selection_and_cost_replay(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "replay"
    result = subprocess.run([sys.executable, str(root / "scripts/verify_final_process.py"),
                             "--output", str(output)], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output / "verification.json").read_text())
    assert report["replay"]["runs"] == 560
    assert report["replay"]["selected_bam"]["identical_bam_callbacks"] == 3430
    assert report["preservation"]["missing_or_changed_experimental_artifacts"] == 0
    assert not report["new_optimization_or_nlp_experiments"]


def test_legacy_roundoff_is_reported_without_rewriting(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier.sys, "version_info", (3, 11))
    actual = tmp_path / "run_results.csv"
    expected = tmp_path / "expected.csv"
    expected.write_text("reconstructed_total_s,category\n1.0,target_reached\n")
    raw = f"reconstructed_total_s,category\n{math.nextafter(1.0, 2.0)},target_reached\n"
    actual.write_text(raw)
    differences = verifier.compare_table(actual, expected)
    assert differences[0]["ulps"] == 1
    assert actual.read_text() == raw
    actual.write_text(raw.replace("target_reached", "target_not_reached"))
    with pytest.raises(ValueError, match="Non-time cell"):
        verifier.compare_table(actual, expected)
    actual.write_text("reconstructed_total_s,category\n1.001,target_reached\n")
    with pytest.raises(ValueError, match="exceeds sum roundoff"):
        verifier.compare_table(actual, expected)
