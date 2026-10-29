"""Verify saved records only; never import an optimizer or execute archived code."""

import argparse
import json
from pathlib import Path, PurePosixPath
import tempfile
from zipfile import ZipFile

from protocol import analyze, read, require, sha


def verify(directory):
    directory = Path(directory).resolve()
    hashes = read(directory / "OUTPUT_SHA256SUMS.json")
    present = {
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    require(
        present == set(hashes) | {"OUTPUT_SHA256SUMS.json"},
        "Output inventory coverage differs",
    )
    for name, digest in hashes.items():
        p = (directory / name).resolve()
        require(
            p.is_relative_to(directory) and sha(p) == digest,
            "Output SHA256 mismatch: " + name,
        )
    manifest = read(directory / "execution_manifest.json")
    require(
        manifest["input_seal"] == sha(directory / "reproduction/SHA256SUMS.json"),
        "Execution input seal changed",
    )
    require(
        manifest["process_jobs"] == manifest["other_method_jobs"] == 0,
        "Non-Grid execution recorded",
    )
    for name in (
        "OMP_NUM_THREADS",
        "OMP_THREAD_LIMIT",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "GOTO_NUM_THREADS",
        "NUMEXPR_MAX_THREADS",
    ):
        require(manifest["threads"][name] == "1", "Thread policy differs")
    selected_cpus = set()
    for session in manifest["sessions"]:
        if "cpu_allocation" not in session:
            continue
        a = session["cpu_allocation"]
        cpu = a["selected_cpu"]
        selected_cpus.add(cpu)
        require(
            a["physical_core_observed_idle"]
            and a["exclusive_reservation"] is False
            and a["effective_cpus"] == [cpu],
            "CPU provenance mismatch",
        )
        require(
            all(
                len(a["smt_sibling_busy_percent"][str(c)]) == 3
                and all(v <= 5 for v in a["smt_sibling_busy_percent"][str(c)])
                for c in a["smt_siblings"]
            ),
            "Idle SMT pair observation mismatch",
        )
    for run_dir in (
        (directory / "runs").iterdir() if (directory / "runs").exists() else ()
    ):
        process = read(run_dir / "process.json")
        require(
            process["cpu"] in selected_cpus,
            "Worker CPU has no recorded idle-core allocation",
        )
        complete = read(run_dir / "COMPLETE.json")
        require(
            complete["input_seal"] == manifest["input_seal"],
            "Completion marker refers to another input seal",
        )
        for name, digest in complete["files"].items():
            require(
                sha(run_dir / name) == digest, "Completed run hash mismatch: " + name
            )
    report = analyze(directory / "reproduction", directory, save=False)
    require(manifest["verification"] == report, "Execution manifest summary mismatch")
    return dict(
        **report,
        output_hashes_verified=len(hashes),
        input_hashes_verified=len(read(directory / "reproduction/SHA256SUMS.json")),
        mode="stored data only; no search, solver, subprocess, or archived-code execution",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--results", type=Path)
    g.add_argument("--archive", type=Path)
    a = p.parse_args()
    if a.archive:
        with (
            ZipFile(a.archive) as z,
            tempfile.TemporaryDirectory(prefix="dsda-grid-data-audit-") as tmp,
        ):
            names = z.namelist()
            require(
                len(names) == len(set(names))
                and all(
                    not PurePosixPath(n).is_absolute()
                    and ".." not in PurePosixPath(n).parts
                    for n in names
                ),
                "Unsafe or duplicate ZIP member",
            )
            roots = {n.split("/")[0] for n in names}
            require(len(roots) == 1, "Expected one returned result root")
            for name in names:
                target = Path(tmp) / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
            report = verify(Path(tmp) / roots.pop())
    else:
        report = verify(a.results)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)
