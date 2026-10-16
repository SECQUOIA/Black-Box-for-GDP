"""Final comparison can be reconstructed without process or DFO solvers."""

import json
from pathlib import Path
import subprocess
import sys


def test_final_process_sources_selection_and_cost_replay(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "replay"
    subprocess.run([sys.executable, str(root / "scripts/verify_final_process.py"),
                    "--output", str(output)], cwd=root, check=True, capture_output=True, text=True)
    report = json.loads((output / "verification.json").read_text())
    assert report["replay"]["runs"] == 560
    assert report["replay"]["selected_bam"]["identical_bam_callbacks"] == 3430
    assert report["preservation"]["missing_or_changed_experimental_artifacts"] == 0
    assert not report["new_optimization_or_nlp_experiments"]
