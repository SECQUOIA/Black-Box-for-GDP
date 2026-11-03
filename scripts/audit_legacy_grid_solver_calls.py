"""Count recorded benchmark solver calls in the three preserved BARON-configured Grid runs.

Uses only the standard library; does not extract archives or invoke solvers.
Preflight and point-enumeration journals are outside the benchmark scope.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {
    "grid_gdp_run_20261008_210901_dw5vq37s.zip": "fb5d962307731a84d5833b1065cd5e94772bdb15c8a4a7f5d05b3ff0b67a7c94",
    "grid_gdp_retry_all_20261009_153057_czhvd9w7.zip": "059453681d8c2b326dcd622d97f6ddb59e815ca8d78ff798e5775f90e42a84be",
    "grid_gdp_retry_fixed_all_20261009_204028_lu6vdgkt.zip": "2215cca4babfa79cf71b874c47218502b4937380cb38956c61e163a6b5436e1e",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(path, expected_sha):
    require(digest(path.read_bytes()) == expected_sha, f"Archive hash mismatch: {path}")
    sidecar = path.with_suffix(".zip.sha256").read_text().split()
    require(sidecar == [expected_sha, f"results/archives/{path.name}"], "Sidecar mismatch")
    jobs = []
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None, "Archive CRC failure")
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate archive members")
        prefix = names[0].split("/")[0] + "/"
        manifest = archive.read(prefix + "SHA256SUMS").decode().splitlines()
        for line in manifest:
            sha, member = line.split("  ", 1)
            require(digest(archive.read(prefix + member)) == sha, f"Member hash mismatch: {member}")
        for member in sorted(names):
            if not member.startswith(prefix + "benchmark/") or not member.endswith("/solver_calls.jsonl"):
                continue
            job = member.rsplit("/", 1)[0] + "/"
            calls = [json.loads(line) for line in archive.read(member).decode().splitlines() if line.strip()]
            result = json.loads(archive.read(job + "result.json"))
            jobs.append({
                "grid_name": result["grid_name"], "method": result["method"],
                "journal_member": member, "result_member": job + "result.json",
                "status": result["status"], "termination": result.get("termination"),
                "configured_solver_policy": result.get("solver_policy"),
                "recorded_solver_calls": len(calls),
                "actual_solver_counts": dict(sorted(Counter(c["solver"] for c in calls).items())),
                "actual_solver_model_type_counts": dict(sorted(Counter(
                    f"{c['solver']}/{c['mtype']}" for c in calls).items())),
                "call_status_counts": dict(sorted(Counter(c["status"] for c in calls).items())),
            })
    summary = []
    for method in sorted({job["method"] for job in jobs}):
        selected = [job for job in jobs if job["method"] == method]
        counts = Counter()
        for job in selected:
            counts.update(job["actual_solver_model_type_counts"])
        summary.append({"method": method, "jobs_with_call_journals": len(selected),
                        "recorded_solver_calls": sum(counts.values()),
                        "actual_solver_model_type_counts": dict(sorted(counts.items()))})
    return {"archive": path.name, "sha256": expected_sha,
            "internal_checksums_verified": len(manifest), "summary": summary, "jobs": jobs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {
        "scope": "Recorded benchmark solver_calls.jsonl entries only; excludes preflight and point enumeration",
        "count_interpretation": "Counts call records, including failed calls; does not imply successful solves",
        "retry_interpretation": "Archives are separate attempts, not additional unique benchmark cases",
        "optimization_solver_calls_during_audit": 0,
        "analysis_source_sha256": digest(Path(__file__).read_bytes()),
        "archives": [audit(ROOT / "results/archives" / name, sha) for name, sha in ARCHIVES.items()],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps([{k: a[k] for k in ("archive", "summary")} for a in report["archives"]], indent=2))


if __name__ == "__main__":
    main()
