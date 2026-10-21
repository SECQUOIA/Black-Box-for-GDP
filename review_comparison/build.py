"""Build a self-contained execution bundle from verified historical artifacts."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

from .common import csvrows, read, save, sha, METHODS

ROOT = Path(__file__).resolve().parents[1]
PROCESS = ROOT / "results/process_ipopt_bam_v2_20261015"
GRID_ARCHIVE = ROOT / "results/archives/grid_trace_rbfopt_20261008_190603_og2app39.zip"
BAM_ARCHIVE = ROOT / "results/archives/grid_trace_bam_20261008_190603_5bh3y_t5.zip"
PILOT = [
    ("grid", "ackley", 10),
    ("grid", "rosenbrock", 100),
    ("process", "column", 16),
    ("process", "cstr_30", 43),
    ("process", "small_batch", 10),
    *[("process", "dynamic", b) for b in (12, 15, 20, 30, 37, 50)],
]


def archive(path):
    # All source archives must be pinned by a recorded sidecar or integration inventory.
    sidecar = Path(str(path) + ".sha256")
    if sidecar.exists():
        expected = sidecar.read_text().split()[0]
    else:
        manifest = read(PROCESS / "integration/manifest.json")
        raw = json.dumps(manifest)
        expected = sha(path)
        if expected not in raw:
            raise ValueError(f"Archive not pinned by integration manifest: {path}")
    if sha(path) != expected:
        raise ValueError(f"Archive hash mismatch: {path}")
    z = zipfile.ZipFile(path)
    names = [n for n in z.namelist() if not n.endswith("/")]
    prefix = names[0].split("/")[0] + "/"
    if len(names) != len(set(names)) or not all(n.startswith(prefix) for n in names):
        raise ValueError("Ambiguous archive root/members")
    data = {n[len(prefix) :]: z.read(n) for n in names}
    if "SHA256SUMS" in data:
        for line in data["SHA256SUMS"].decode().splitlines():
            digest, name = line.split(maxsplit=1)
            if hashlib.sha256(data[name.lstrip("*")]).hexdigest() != digest:
                raise ValueError(f"Archive member changed: {name}")
    z.close()
    return data, {
        "path": str(path.relative_to(ROOT)),
        "sha256": expected,
        "archive_root": prefix.rstrip("/"),
    }


def put(root, name, data):
    path = root / name
    if ".." in Path(name).parts or Path(name).is_absolute():
        raise ValueError("Unsafe bundle path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def build(output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    with tempfile.TemporaryDirectory(prefix="review-build-") as temporary:
        dest = Path(temporary) / "review_comparison_runner"
        dest.mkdir()
        sources = []
        for f in sorted((ROOT / "review_comparison").glob("*.py")):
            put(dest, "review_comparison/" + f.name, f.read_bytes())
        for f in sorted((ROOT / "review_comparison/validation").glob("*")):
            if f.is_file():
                put(dest, "review_comparison/validation/" + f.name, f.read_bytes())
        for name in (
            "cpu_affinity.py",
            "run_review_comparison_dantzig.sh",
            "docs/review_comparison_dantzig.md",
            "docs/review_comparison_status.md",
            "docs/review_comparison_draft.tex",
            "tests/test_review_comparison.py",
            "LICENSE",
        ):
            put(dest, name, (ROOT / name).read_bytes())
        grid, provenance = archive(GRID_ARCHIVE)
        sources.append(provenance)
        for name, data in grid.items():
            if name.startswith("source/"):
                put(dest, "frozen/grid/" + name[7:], data)
        grid_run = json.loads(grid["run.json"])
        save(dest / "evidence/grid_run.json", grid_run)
        bam, provenance = archive(BAM_ARCHIVE)
        sources.append(provenance)
        predetermined, evidence = {}, []
        for name in sorted(bam):
            if not name.startswith("jobs/") or not name.endswith("/result.json"):
                continue
            result = json.loads(bam[name])
            trace = name.removesuffix("result.json") + result["trace"]["path"]
            if hashlib.sha256(bam[trace]).hexdigest() != result["trace"]["sha256"]:
                raise ValueError("BAM trace hash")
            events = [json.loads(line) for line in bam[trace].splitlines()][1:-1]
            spec = result["spec"]
            if [e["point"] for e in events[:3]] != spec["starting_points"]:
                raise ValueError("BAM shared initialization mismatch")
            # Freeze the observed ten-point invariant prefix, not a regenerated Sobol design.
            prefix = [e["point"] for e in events[3:13]]
            key = (Path(spec["csv_name"]).stem, spec["max_evaluations"], spec["seed"])
            predetermined[key] = prefix
            evidence.append(
                {
                    "key": key,
                    "points": prefix,
                    "trace_member": trace,
                    "trace_sha256": result["trace"]["sha256"],
                    "next_point": events[13]["point"] if len(events) > 13 else None,
                }
            )
        if len(predetermined) != 1050:
            raise ValueError("Incomplete BAM trace inventory")
        full = [e for e in evidence if e["key"][1] > 10]
        if (
            len({json.dumps(e["points"]) for e in full}) != 1
            or len({tuple(e["next_point"]) for e in full}) < 2
        ):
            raise ValueError("Ten-point invariant-prefix evidence changed")
        template = full[0]["points"]
        if len(template) != 10 or any(
            e["points"] != template[: len(e["points"])] for e in evidence
        ):
            raise ValueError("BAM prefix mismatch")
        save(
            dest / "evidence/bam_predetermined.json",
            {
                "selection": "callbacks 4..13, budget truncated; next callback varies",
                "not_a_claim_about_unrecorded_BAM_internals": True,
                "records": evidence,
            },
        )
        # Full final process inventory, retaining the original objective and cost attempt.
        process_meta, process_runs = {}, csvrows(PROCESS / "tables/run_results.csv")
        if Counter(r["category"] for r in process_runs) != {
            "target_reached": 291,
            "target_not_reached": 268,
            "execution_failed": 1,
        }:
            raise ValueError("Final Process selection changed")
        for kind, label in [
            ("cstr", "cstr_20261015_174637_r1dzn5tk"),
            ("non_cstr", "non_cstr_20261015_172428_o671edu_"),
        ]:
            returned, prov = archive(ROOT / f"results/archives/ipopt_dfo_{label}.zip")
            sources.append(prov)
            for name, data in returned.items():
                if name.startswith("reproduction/"):
                    put(dest, f"frozen/{kind}/" + name[len("reproduction/") :], data)
            original_run = json.loads(returned["run.json"])
            save(dest / f"evidence/{kind}_run.json", original_run)
            for name, data in returned.items():
                if name.startswith("jobs/") and name.endswith("/spec.json"):
                    spec = json.loads(data)
                    if spec["method"] != "rbfopt":
                        continue
                    directory = name.removesuffix("spec.json")
                    process_meta[spec["job_id"]] = {
                        "spec": spec,
                        "kind": kind,
                        "settings": json.loads(
                            returned[directory + "actual_settings.json"]
                        ),
                        "runtime": json.loads(returned[directory + "runtime.json"]),
                        "hard_seconds": original_run["config"]["hard_seconds"],
                    }
        if len(process_meta) != 140:
            raise ValueError("Expected 140 original RBFOpt specs")
        process_cost_count = 0
        for f in sorted((PROCESS / "tables").glob("cost_table_*.csv")):
            rows = csvrows(f)
            case = f.stem.removeprefix("cost_table_")
            originals = (
                dest
                / ("frozen/cstr" if case.startswith("cstr_") else "frozen/non_cstr")
                / f"inputs/{case}/evaluations.csv"
            )
            old = {tuple(json.loads(r["point"])): r for r in csvrows(originals)}
            for r in rows:
                pt = tuple(json.loads(r["point"]))
                if pt in old:
                    for field in (
                        "accepted",
                        "objective",
                        "total_wall_s",
                        "status",
                        "termination",
                    ):
                        if old[pt][field] != r[field]:
                            raise ValueError(
                                f"Final cost table changes original {case}/{pt}/{field}"
                            )
                elif (
                    r["accepted"] != "False"
                    or r["objective"]
                    or r["termination"] != "not_solved"
                ):
                    raise ValueError("Only structural supplement rows permitted")
            put(dest, "data/" + f.name, f.read_bytes())
            process_cost_count += len(rows)
        if process_cost_count != 2455:
            raise ValueError("Incomplete final Process costs")
        for name in (
            "integration/manifest.json",
            "source_manifest.json",
            "timing_audit.json",
            "replacement_verification.json",
        ):
            put(dest, "evidence/process/" + name, (PROCESS / name).read_bytes())
        put(
            dest,
            "data/grid_point_timings.csv",
            (ROOT / "results/grid_gdp_20261009/raw/point_timings.csv").read_bytes(),
        )
        put(
            dest,
            "data/historical_grid_runs.csv",
            (ROOT / "results/grid_gdp_dfo_20261011/runs.csv").read_bytes(),
        )
        put(
            dest,
            "data/historical_process_runs.csv",
            (PROCESS / "tables/run_results.csv").read_bytes(),
        )
        # Expected settings: RBFOpt defaults are recorded for every Process job.
        settings_template = next(iter(process_meta.values()))["settings"]
        jobs = []
        for spec in grid_run["plan"]:
            case = Path(spec["csv_name"]).stem
            b, seed = spec["max_evaluations"], spec["seed"]
            settings = {**settings_template, "max_evaluations": b, "rand_seed": seed}
            job = {
                "scope": "grid",
                "case": case,
                "budget": b,
                "seed": seed,
                "lower": [0, 0],
                "upper": [30, 30],
                "starts": spec["starting_points"],
                "frozen_kind": "grid",
                "original_spec": spec,
                "reference_settings": settings,
                "hard_seconds": 0,
                "reference_runtime": grid_run["runtime"],
                "predetermined": predetermined[case, b, seed],
            }
            for method in METHODS:
                jobs.append(
                    {
                        **job,
                        "method": method,
                        "job_id": f"grid_{case}_B{b}_seed{seed}_{method}",
                    }
                )
        for meta in process_meta.values():
            spec = meta["spec"]
            job = {
                "scope": "process",
                "case": spec["case"],
                "budget": spec["budget"],
                "seed": spec["seed"],
                "lower": spec["lower"],
                "upper": spec["upper"],
                "starts": spec["starts"],
                "frozen_kind": meta["kind"],
                "original_spec": spec,
                "reference_settings": meta["settings"],
                "reference_runtime": meta["runtime"],
                "hard_seconds": meta["hard_seconds"],
                "predetermined": [],
            }
            for method in METHODS[:2]:
                jobs.append(
                    {
                        **job,
                        "method": method,
                        "job_id": spec["job_id"].removesuffix("rbfopt") + method,
                    }
                )
        for job in jobs:
            job["pilot"] = (
                job["seed"] == 0 and (job["scope"], job["case"], job["budget"]) in PILOT
            )
            job["priority"] = job["scope"] == "process" and job["case"] in (
                "column",
                "cstr_30",
                "small_batch",
                "dynamic",
            )
        jobs.sort(
            key=lambda j: (
                not j["priority"],
                j["scope"],
                j["case"],
                j["budget"],
                j["seed"],
                j["method"],
            )
        )
        if Counter(j["method"] for j in jobs) != dict(zip(METHODS, [1190, 1190, 1050])):
            raise ValueError("Unexpected plan size")
        save(dest / "plan.json", jobs)
        save(
            dest / "evidence/source_provenance.json",
            {
                "provider_revision": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "historical_archives": sources,
                "process_points": process_cost_count,
                "pilot_rule": "seed 0; ackley B10, rosenbrock B100; Column16/CSTR30-43/SmallBatch10/Dynamic12,15,20,30,37,50",
                "source_dirty_status": subprocess.check_output(
                    ["git", "status", "--short"], cwd=ROOT, text=True
                ).strip(),
            },
        )
        # Retain exact raw data hashes alongside current generated plan; no licenses or binaries.
        inventory = {
            p.relative_to(dest).as_posix(): sha(p)
            for p in sorted(dest.rglob("*"))
            if p.is_file()
        }
        save(dest / "inventory.json", {"files_sha256": inventory})
        from .runner import check_inputs

        report = check_inputs(dest)
        save(dest / "build_validation.json", report)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(dest.rglob("*")):
                if p.is_file():
                    info = zipfile.ZipInfo(
                        "review_comparison_runner/" + p.relative_to(dest).as_posix(),
                        (2026, 10, 20, 0, 0, 0),
                    )
                    info.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(info, p.read_bytes())
        Path(str(output) + ".sha256").write_text(f"{sha(output)}  {output.name}\n")
        save(
            Path(str(output) + ".manifest.json"),
            {
                "zip_sha256": sha(output),
                "validation": report,
                "files_sha256": inventory,
            },
        )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(build(parser.parse_args().output))
