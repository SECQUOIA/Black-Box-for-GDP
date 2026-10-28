"""Prepare a fresh sealed D-SDA experiment inside the Dantzig repository."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import sys
import traceback


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REFERENCE = HERE / "reference"
RUNTIME_FILES = (
    "run.py",
    "test_repository_identity.py",
    "test_shared_cpu.py",
    "select_dsda_cpu.py",
    "test_idle_launch.py",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def reference_inventory():
    origin = json.loads((HERE / "reference_origin.json").read_text())
    seal = REFERENCE / "SHA256SUMS.json"
    if sha(seal) != origin["reference_seal_sha256"]:
        raise ValueError("Retained reference seal changed")
    inventory = json.loads(seal.read_text())
    for name, digest in inventory.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid reference path: " + name)
        if sha(REFERENCE / name) != digest:
            raise ValueError("Retained reference changed: " + name)
    return inventory, origin


def prepare(output=None):
    inventory, origin = reference_inventory()
    now = datetime.now(timezone.utc)
    tag = now.strftime("%Y%m%d_%H%M%S") + "_" + str(os.getpid())
    output = (
        Path(output).resolve()
        if output
        else REPO / "results" / ("dsda_abs1e5_input_" + tag)
    )
    results = (REPO / "results").resolve()
    if not output.is_relative_to(results) or output == results:
        raise ValueError(
            "Prepared inputs must be a new directory under repository/results"
        )
    results.mkdir(exist_ok=True)
    if output.exists():
        raise FileExistsError(
            "Prepared directory already exists; nothing overwritten: " + str(output)
        )
    output.mkdir()
    try:
        for name in inventory:
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REFERENCE / name, target)
        shutil.copy2(
            REFERENCE / "SHA256SUMS.json", output / "retained_reference_SHA256SUMS.json"
        )
        for name in RUNTIME_FILES:
            shutil.copy2(HERE / name, output / name)
        (output / "workflow").mkdir()
        for name in ("prepare.py", "launch.py", "README.md", "reference_origin.json"):
            shutil.copy2(HERE / name, output / "workflow" / name)
        (output / "README.md").write_text(
            "# Prepared D-SDA absolute improvement tolerance experiment\n\n"
            "This is a new sealed input snapshot prepared inside the Dantzig repository.\n"
            "The retained reference preserves the previously validated 1190-pair cohort.\n"
            "The experiment uses absolute improvement 1e-5, unchanged ties and target stopping, stored responses only, and one CPU selected after an idle-core check with one numerical-library thread.\n"
            "Preparation does not launch the full experiment or call NLP solvers.\n"
            "The permanent workflow and usage instructions are in experiments/dsda_abs1e5/README.md.\n"
        )
        manifest = json.loads((output / "manifest.json").read_text())
        manifest["repository_preparation"] = dict(
            utc_prepared=now.isoformat(),
            repository=str(REPO),
            source_directory=str(HERE),
            reference=origin,
            workflow_source_sha256={
                name: sha(HERE / name)
                for name in ("prepare.py", "launch.py", *RUNTIME_FILES)
            },
            full_experiment_started=False,
            note="Only storage and repeat-run output handling changed; the algorithm, lookup data, baseline, seeds, starts, budgets and success rules retain their verified values.",
        )
        write(output / "manifest.json", manifest)
        hashes = {
            str(p.relative_to(output)): sha(p)
            for p in sorted(output.rglob("*"))
            if p.is_file() and p.name != "SHA256SUMS.json"
        }
        write(output / "SHA256SUMS.json", hashes)
        record = dict(
            status="validating",
            full_experiment_started=False,
            input_directory=str(output),
            source_directory=str(HERE),
            reference_archive_sha256=origin["archive_sha256"],
            preparation_commands=[],
            expected_runs=1190,
            new_nlp_calls=0,
        )
        command_sets = [
            [sys.executable, str(output / "run.py"), "verify"],
            [sys.executable, str(output / "test_repository_identity.py")],
            [sys.executable, str(output / "test_shared_cpu.py")],
            [sys.executable, str(output / "select_dsda_cpu.py"), "--self-test"],
            [sys.executable, str(output / "test_idle_launch.py")],
            [sys.executable, str(output / "test_experiment.py")],
        ]
        for index, command in enumerate(command_sets, 1):
            log = output / f"preparation_check_{index}.log"
            with log.open("x") as stream:
                completed = subprocess.run(
                    command,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                )
            record["preparation_commands"].append(
                dict(command=command, returncode=completed.returncode, log=log.name)
            )
            print(
                f"Preparation check {index}/{len(command_sets)}: {'PASS' if completed.returncode == 0 else 'FAIL'}",
                flush=True,
            )
            if completed.returncode:
                raise RuntimeError("Preparation check failed; read " + str(log))
        for name in inventory:
            if name.startswith(
                ("inputs/", "frozen/", "original/", "validation/legacy/")
            ):
                if sha(output / name) != inventory[name]:
                    raise ValueError(
                        "Scientific reference changed during preparation: " + name
                    )
        record["status"] = "ready"
        run_command = [
            str(REPO / ".venv-dantzig/bin/python"),
            str(HERE / "run.py"),
            "server",
            "--repo",
            str(REPO),
            "--input",
            str(output),
        ]
        record["run_command"] = run_command
        write(output / "PREPARATION.json", record)
        hashes = {
            str(p.relative_to(output)): sha(p)
            for p in sorted(output.rglob("*"))
            if p.is_file() and p.name != "SHA256SUMS.json"
        }
        write(output / "SHA256SUMS.json", hashes)
        print("PREPARED INPUT:", output, flush=True)
        print("FULL EXPERIMENT HAS NOT STARTED", flush=True)
        print("RUN WHEN READY:", shlex.join(run_command), flush=True)
        return output
    except Exception:
        (output / "PREPARATION_ERROR.txt").write_text(traceback.format_exc())
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="Optional new directory under repository/results"
    )
    args = parser.parse_args()
    prepare(args.output)
