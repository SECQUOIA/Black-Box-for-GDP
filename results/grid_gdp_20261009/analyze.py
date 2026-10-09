"""Verify the supplied Grid GDP archive and summarize recorded times; no solves."""

import csv
import hashlib
import io
import json
import math
import statistics
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path


HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parent / "archives/grid_gdp_run_20261008_210901_dw5vq37s.zip"
FIELDS = (
    "point_wall_s", "solver_call_wall_s", "gams_solve_s", "ipopt_reported_s",
    "preparation_wall_s", "verification_wall_s", "recording_and_cleanup_wall_s",
)


def stats(values):
    values = sorted(values)
    assert values and all(math.isfinite(v) and v >= 0 for v in values)

    def quantile(p):
        index = (len(values) - 1) * p
        lower = int(index)
        upper = min(lower + 1, len(values) - 1)
        return values[lower] + (values[upper] - values[lower]) * (index - lower)

    return {
        "n": len(values), "sum": math.fsum(values),
        "mean": statistics.fmean(values), "median": statistics.median(values),
        "min": values[0], "p95": quantile(.95), "p99": quantile(.99),
        "max": values[-1],
    }


def elapsed(start, end):
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def main():
    archive_hash = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    assert archive_hash == Path(str(ARCHIVE) + ".sha256").read_text().split()[0]
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert archive.testzip() is None
        root = ARCHIVE.stem + "/"
        manifest = {
            name.lstrip("*"): digest
            for line in archive.read(root + "SHA256SUMS").decode().splitlines()
            for digest, name in [line.split(maxsplit=1)]
        }
        assert set(archive.namelist()) == {root + n for n in manifest} | {root + "SHA256SUMS"}
        for name, digest in manifest.items():
            assert hashlib.sha256(archive.read(root + name)).hexdigest() == digest, name
        for path in (HERE / "raw").iterdir():
            assert path.read_bytes() == archive.read(root + path.name), path.name

        def data(name):
            return json.loads(archive.read(root + name))

        def table(name):
            return list(csv.DictReader(io.StringIO(archive.read(root + name).decode())))

        run = data("run.json")
        original_summary = data("summary.json")
        points = table("point_timings.csv")
        benchmarks = table("benchmark.csv")
        names = run["config"]["grids"]
        methods = run["config"]["methods"]
        assert len(names) == 21 and len(points) == 20181
        assert len(benchmarks) == 105
        assert {(r["grid_name"], r["method"]) for r in benchmarks} == {
            (name, method) for name in names for method in methods
        }
        lookup = {(r["grid_name"], int(r["flat_index"])): r for r in points}
        assert len(lookup) == len(points)
        for name in names:
            rows = [r for r in points if r["grid_name"] == name]
            assert len(rows) == 961
            assert {int(r["flat_index"]) for r in rows} == set(range(961))
            assert {tuple(json.loads(r["point"])) for r in rows} == {
                (i, j) for i in range(31) for j in range(31)
            }
            journal = archive.read(root + f"points/{name}/evaluations.jsonl").decode().splitlines()
            assert len(journal) == 961
            for line in journal:
                record = json.loads(line)["record"]
                row = lookup[(name, record["flat_index"])]
                assert record["point"] == json.loads(row["point"])
                for field in FIELDS:
                    assert record[field] == float(row[field])
        assert all(
            r["accepted"] == "True" and r["ipopt_invoked"] == "True"
            and r["threads"] == "1" and r["status"] == "completed"
            and r["original_free_variables"] == "0" for r in points
        )
        assert all(r["terminal_verified"] == "True" for r in benchmarks)
        for row in benchmarks:
            result = data(f"benchmark/{row['grid_name']}/{row['method']}/result.json")
            assert result["status"] == row["status"]
            if row["worker_wall_s"]:
                assert result["worker_wall_s"] == float(row["worker_wall_s"])

        overall = {field: stats([float(r[field]) for r in points]) for field in FIELDS}
        assert math.isclose(overall["point_wall_s"]["sum"], original_summary["sum_point_evaluation_s"], abs_tol=1e-7)
        active = [r for r in benchmarks if r["worker_wall_s"]]
        assert len(active) == 73
        by_method = {}
        for method in methods:
            rows = [r for r in benchmarks if r["method"] == method]
            times = [float(r["worker_wall_s"]) for r in rows if r["worker_wall_s"]]
            by_method[method] = {
                "scheduled": len(rows), "attempted": len(times),
                "status_counts": dict(Counter(r["status"] for r in rows)),
                "termination_counts": dict(Counter(r["termination"] for r in rows)),
                "worker_wall_s": stats(times),
                "recorded_feasible_incumbents": sum(r["has_feasible_solution"] == "True" for r in rows),
                "recorded_target_hits": sum(r["target_hit"] == "True" for r in rows),
            }
        first_point = data(f"points/{names[0]}/process.json")["utc"]
        last_point = data(f"points/{names[-1]}/complete.json")["utc"]
        first_benchmark = data(f"benchmark/{names[0]}/{methods[0]}/process.json")["utc"]
        report = {
            "archive": str(ARCHIVE.relative_to(HERE.parent)),
            "archive_sha256": archive_hash,
            "verified_member_hashes": len(manifest),
            "verified_point_rows": len(points),
            "units": "seconds unless otherwise stated",
            "quantiles": "linear interpolation at (n - 1) * p",
            "point_timing_scope": original_summary["point_timing_scope"],
            "point_statistics": overall,
            "point_statistics_by_grid": {
                name: stats([float(r["point_wall_s"]) for r in points if r["grid_name"] == name])
                for name in names
            },
            "point_cost_estimates_by_evaluation_budget": {
                str(b): b * overall["point_wall_s"]["mean"] for b in [10, 30, 50, 70, 100]
            },
            "benchmark_status_counts": dict(Counter(r["status"] for r in benchmarks)),
            "benchmark_termination_counts": dict(Counter(r["termination"] for r in benchmarks)),
            "benchmark_worker_wall_s": stats([float(r["worker_wall_s"]) for r in active]),
            "benchmark_by_method": by_method,
            "benchmark_by_grid_s": {
                name: {
                    r["method"]: float(r["worker_wall_s"]) if r["worker_wall_s"] else None
                    for r in benchmarks if r["grid_name"] == name
                } for name in names
            },
            "timestamps_utc": {
                "run_created": run["created_utc"], "first_point_process": first_point,
                "last_point_complete": last_point, "first_benchmark_process": first_benchmark,
                "final_summary": original_summary["utc"],
            },
            "elapsed_to_final_summary_s": elapsed(run["created_utc"], original_summary["utc"]),
            "point_phase_elapsed_s": elapsed(first_point, last_point),
            "benchmark_phase_to_final_summary_s": elapsed(first_benchmark, original_summary["utc"]),
            "interpretation": [
                "Each coordinate was measured once; no optimizer or solver was rerun for this analysis.",
                "All original model variables are fixed for point evaluations.",
                "IPOPT reports 0.001 seconds for every point at three-decimal log precision.",
                "Point times include fresh preparation, the GAMS/IPOPT call, and verification; audit and archival are separate.",
                "Benchmark totals use worker_wall_s, including the hard timeout whose method_wall_s is absent.",
                "Unsupported cases have no measured worker solve time and are excluded from time means.",
                "Feasible incumbent and optimality flags are preserved source reports, not new certificates.",
            ],
        }
    (HERE / "timing_summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "verified_member_hashes": len(manifest), "points": len(points),
        "point_mean_s": overall["point_wall_s"]["mean"],
        "benchmark_worker_total_s": report["benchmark_worker_wall_s"]["sum"],
        "benchmark_status_counts": report["benchmark_status_counts"],
    }))


if __name__ == "__main__":
    main()
