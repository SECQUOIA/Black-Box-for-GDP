"""Exercise the CPU setup wrapper without downloading or installing packages."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != "linux", reason="Dantzig setup requires Linux")
@pytest.mark.parametrize("version", ["2.13.0", "99.0.0"])
def test_setup_installs_manifest_torch_pin_and_runs_preflight(tmp_path, version):
    root = Path(__file__).resolve().parents[1]
    runner = tmp_path / "runner"
    runner.mkdir()
    shutil.copy2(root / "run_fmqa_qhd_dantzig.sh", runner)
    (runner / "requirements-fmqa-qhd.txt").write_text(
        f"# CPU runtime\nnumpy==2.2.6\ntorch=={version}\n"
    )
    environment = tmp_path / "venv"
    (environment / "bin").mkdir(parents=True)
    (environment / "pyvenv.cfg").touch()
    interpreter = environment / "bin/python"
    interpreter.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['SETUP_CALLS'], 'a') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
    )
    interpreter.chmod(0o755)
    calls_path = tmp_path / "calls.jsonl"
    result = subprocess.run(
        ["bash", str(runner / "run_fmqa_qhd_dantzig.sh"), "setup", "--allow-other-host"],
        env={**os.environ, "FMQA_REPOSITORY": str(tmp_path),
             "FMQA_QHD_ENV": str(environment), "FMQA_QHD_BASE_PYTHON": str(interpreter),
             "MPLCONFIGDIR": str(tmp_path / "mpl"), "SETUP_CALLS": str(calls_path)},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
    assert ["-m", "pip", "install", f"torch=={version}", "--index-url",
            "https://download.pytorch.org/whl/cpu"] in calls
    assert ["-m", "pip", "check"] in calls
    assert calls[-1][:2] == ["process_followup_runner.py", "check"]
    assert calls[-1][-1] == "--allow-other-host"
