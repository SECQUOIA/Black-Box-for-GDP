"""Seal a Grid-only package from the second D-SDA return; run no searches."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
from zipfile import ZipFile

from protocol import read, require, sha, validate_cohort, verify_inputs, write

HERE = Path(__file__).resolve().parent


def prepare(repo, archive, output=None):
    repo, archive = Path(repo).resolve(), Path(archive).resolve()
    reference = read(HERE / "BASELINE.json")
    require(sha(archive) == reference["archive_sha256"], "Wrong baseline ZIP hash")
    tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + str(os.getpid())
    out = (
        Path(output).resolve()
        if output
        else repo / "results" / ("dsda_grid_target_stop_input_" + tag)
    )
    require(
        out.is_relative_to(repo / "results") and out != repo / "results",
        "Inputs must be under repository/results",
    )
    require(not out.exists(), "Input directory already exists; nothing overwritten")
    out.mkdir(parents=True)
    prefix = reference["prefix"]
    copied = {}
    with ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)), "Duplicate baseline ZIP member")
        require(
            all(
                not PurePosixPath(n).is_absolute()
                and ".." not in PurePosixPath(n).parts
                for n in names
            ),
            "Unsafe ZIP member",
        )
        output_hashes = json.loads(z.read(prefix + "OUTPUT_SHA256SUMS.json"))
        input_hashes = json.loads(z.read(prefix + "reproduction/SHA256SUMS.json"))
        for name, h in output_hashes.items():
            require(
                hashlib.sha256(z.read(prefix + name)).hexdigest() == h,
                "Baseline output hash mismatch: " + name,
            )
        for name, h in input_hashes.items():
            require(
                hashlib.sha256(z.read(prefix + "reproduction/" + name)).hexdigest()
                == h,
                "Baseline input/source mismatch: " + name,
            )
        all_jobs = json.loads(z.read(prefix + "reproduction/inputs/jobs.json"))
        jobs = [
            {k: j[k] for k in ("spec", "target", "hard_seconds")}
            for j in all_jobs
            if j["spec"]["scope"] == "grid"
        ]
        validate_cohort(jobs)
        write(out / "inputs/jobs.json", jobs)

        def extract(member, destination):
            data = z.read(prefix + member)
            target = out / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            copied[destination] = dict(
                archive_member=prefix + member, sha256=hashlib.sha256(data).hexdigest()
            )

        for case in sorted({j["spec"]["case"] for j in jobs}):
            extract(
                "reproduction/inputs/grids/" + case + ".csv",
                "inputs/grids/" + case + ".csv",
            )
        for job in jobs:
            for name in ("result.json", "callbacks.jsonl"):
                suffix = job["spec"]["job_id"] + "/" + name
                extract("runs/" + suffix, "baseline_runs/" + suffix)
        extract("reproduction/grid_dsda.py", "baseline_source/grid_dsda.py")
        for name in (
            "instrumentation.py",
            "evaluation_trace.py",
            "adopted_analysis.py",
            "select_dsda_cpu.py",
        ):
            require(
                (HERE / name).read_bytes() == z.read(prefix + "reproduction/" + name),
                "Retained support source differs: " + name,
            )
        extract("reproduction/SHA256SUMS.json", "baseline_source/SHA256SUMS.json")
        extract("execution_manifest.json", "baseline_source/execution_manifest.json")
    for name in source_files():
        shutil.copy2(HERE / name, out / name)
    write(
        out / "INPUT_MANIFEST.json",
        dict(
            experiment="Grid D-SDA common-success target stopping",
            baseline=reference,
            prepared_utc=datetime.now(timezone.utc).isoformat(),
            repository=str(repo),
            source_directory=str(HERE),
            expected=1050,
            process_jobs=0,
            other_method_jobs=0,
            improvement_abs_tol=1e-5,
            target_stop="adopted_analysis.hit",
            copied_baseline_members=copied,
            source_sha256={n: sha(HERE / n) for n in source_files()},
        ),
    )
    inventory = {
        str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()
    }
    write(out / "SHA256SUMS.json", inventory)
    verify_inputs(out)
    print("PREPARED_GRID_ONLY", out, flush=True)
    return out


def source_files():
    return sorted(
        p.name
        for p in HERE.iterdir()
        if p.is_file() and (p.suffix in (".py", ".md") or p.name == "BASELINE.json")
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True, type=Path)
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    prepare(a.repo, a.archive, a.output)
