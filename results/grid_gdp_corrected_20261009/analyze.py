"""Reproduce the corrected ten-case audit from archived evidence; no solves."""
from collections import Counter
from datetime import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import types
import zipfile

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent
RUN = "grid_gdp_retry_fixed_all_20261009_204028_lu6vdgkt"
PROFILE = "pyomo610-grid-v1"

# Reuse the already published byte/hash verification and CSV helpers.
spec = importlib.util.spec_from_file_location(
    "retry_audit", RESULTS / "grid_gdp_retry_20261009/analyze.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def main():
    files, archive_info = audit.archive(RUN)
    parent_files, parent_info = audit.archive(audit.RETRY)
    original_files, original_info = audit.archive(audit.ORIGINAL)
    run = json.loads(files["run.json"])
    parent = json.loads(parent_files["run.json"])
    original = json.loads(original_files["run.json"])
    summary = json.loads(files["summary.json"])
    digest = lambda data: hashlib.sha256(data).hexdigest()
    assert run["retry_of"]["source_run_json_sha256"] == digest(parent_files["run.json"])
    assert run["runtime"] == parent["runtime"] == original["runtime"]
    assert run["config"]["retry_fix_profile"] == PROFILE
    assert run["config"]["phases"] == ["benchmark"]
    assert run["config"]["point_indices"] == []
    for key in ["cpu", "time_limit", "relative_gap", "executable", "gams_version"]:
        assert run["config"][key] == original["config"][key]
    for path in (HERE / "raw").iterdir():
        assert path.read_bytes() == files[path.name]
    package = RESULTS / "runners/grid_gdp_error_fix_runner.zip"
    assert digest(package.read_bytes()) == Path(str(package) + ".sha256").read_text().split()[0]
    with zipfile.ZipFile(package) as z:
        for name, sha in run["source_sha256"].items():
            assert digest(files["source/" + name]) == sha
            assert files["source/" + name] == z.read("grid_gdp_runner/" + name)
    assert files["source/gdp_models/grid.py"] == original_files["source/gdp_models/grid.py"]
    for name in run["config"]["grids"]:
        path = f"source/benchmark_grids/{name}.csv"
        assert files[path] == original_files[path]
    for job in run["retry_of"]["jobs"]:
        prefix = f"benchmark/{job['grid_name']}/{job['method']}/"
        for name in ["result", "terminal"]:
            assert digest(parent_files[prefix + name + ".json"]) == job["previous_" + name + "_sha256"]
        assert json.loads(parent_files[prefix + "result.json"])["status"] == "error"

    grid = types.ModuleType("archived_grid")
    grid.__file__ = str(HERE / "archived/gdp_models/grid.py")
    exec(compile(files["source/gdp_models/grid.py"], grid.__file__, "exec"), grid.__dict__)
    pairs = {(j["grid_name"], j["method"]) for j in run["config"]["benchmark_jobs"]}
    expected = {("alpine1", "loa")} | {
        (name, method) for name in ["camel3", "dropwave", "sum_of_squares"]
        for method in ["ric", "gloa", "loa"]}
    raw_rows = audit.table(files["benchmark.csv"])
    assert len(raw_rows) == len(pairs) == 10 and pairs == expected
    assert {(r["grid_name"], r["method"]) for r in raw_rows} == pairs
    rows = []
    for raw in raw_rows:
        name, method = raw["grid_name"], raw["method"]
        prefix = f"benchmark/{name}/{method}/"
        for path, sha in json.loads(files[prefix + "terminal.json"])["files_sha256"].items():
            assert digest(files[prefix + path]) == sha
        record = json.loads(files[prefix + "result.json"])
        solution = json.loads(files[prefix + "solution.json"])
        assert raw["status"] == record["status"] and raw["terminal_verified"] == "True"
        assert float(raw["worker_wall_s"]) == record["worker_wall_s"]
        assert record["retry_fix_profile"] == PROFILE
        m = grid.build_grid_gdp(name, verify_csv=False)
        variables = list(m.component_data_objects(grid.pyo.Var, descend_into=(grid.pyo.Block, grid.Disjunct)))
        assert set(solution["variables"]) == {v.name for v in variables}
        for v in variables:
            value = solution["variables"][v.name]
            assert math.isfinite(value)
            assert v.lb is None or value >= v.lb - 1e-5
            assert v.ub is None or value <= v.ub + 1e-5
            if v.is_binary():
                assert abs(value - round(value)) <= 1e-5
            v.set_value(value, skip_validation=True)
        choices = [[i for i in m.I if grid.pyo.value(c[i].binary_indicator_var) > .5]
                   for c in (m.Xchoice, m.Ychoice)]
        assert all(len(c) == 1 for c in choices)
        point = tuple(c[0] for c in choices)
        fixed = grid.fix_grid_point(grid.build_grid_gdp(name, verify_csv=False), point)
        for v in fixed.component_data_objects(grid.pyo.Var, descend_into=(grid.pyo.Block, grid.Disjunct)):
            assert abs(grid.pyo.value(v) - solution["variables"][v.name]) <= 1e-5
        value = float(grid.pyo.value(fixed.obj))
        assert abs(value - solution["objective"]) <= 1e-12
        reference = {(int(r["x"]), int(r["y"])): float(r["z_norm"])
                     for r in audit.table(files[f"source/benchmark_grids/{name}.csv"])}
        assert len(reference) == 961
        assert abs(value - reference[point]) <= 1e-12
        gap = value - min(reference.values())
        assert gap <= 1e-5
        rows.append({
            "grid_name": name, "method": method, "retry_fix_profile": PROFILE,
            "status": record["status"], "termination": record["termination"],
            "worker_wall_s": record["worker_wall_s"],
            "incumbent_elapsed_s": record["incumbent_elapsed_s"],
            "recorded_target_hit": record.get("target_hit"),
            "audited_feasible": True, "audited_target_hit": gap <= 1e-5,
            "audited_point": json.dumps(point), "audited_objective": value,
            "csv_minimum": min(reference.values()), "audited_gap": gap,
            "global_optimality_certified": record["global_optimality_certified"],
            "source_archive": RUN + ".zip", "source_result": prefix + "result.json",
            "source_result_sha256": digest(files[prefix + "result.json"]),
        })
    statuses = dict(Counter(r["status"] for r in rows))
    terminations = dict(Counter(r["termination"] for r in rows))
    assert statuses == {"finished": 9, "hard_time_limit": 1}
    assert terminations == {"optimal": 7, "maxTimeLimit": 3}
    assert summary["error_benchmarks"] == 0 and summary["all_jobs_finished"]
    point_data = RESULTS / "grid_gdp_20261009/raw/point_timings.csv"
    assert point_data.read_bytes() == original_files["point_timings.csv"]
    assert len(audit.table(point_data.read_bytes())) == 20181
    report = {
        "archive": archive_info, "parent_archive": parent_info,
        "original_archive": original_info,
        "runner_package_sha256": digest(package.read_bytes()),
        "verified_source_files": len(run["source_sha256"]),
        "retry_fix_profile": PROFILE, "runtime_matches_parent": True,
        "status_counts": statuses, "termination_counts": terminations,
        "audited_feasible": 10, "audited_target_hits": 10,
        "worker_total_s": math.fsum(r["worker_wall_s"] for r in rows),
        "elapsed_to_final_summary_s": (datetime.fromisoformat(summary["utc"])
                                       - datetime.fromisoformat(run["created_utc"])).total_seconds(),
        "created_utc": run["created_utc"], "final_summary_utc": summary["utc"],
        "point_data": str(point_data.relative_to(RESULTS)),
        "point_data_sha256": digest(point_data.read_bytes()),
        "ipopt_points": 20181, "new_point_measurements": 0,
        "policy": "Publish all ten corrected attempts separately. Do not overwrite original or unchanged-profile retry outcomes. Preserve original target flags; independently audit saved solutions, including the hard-timeout incumbent.",
    }
    audit.write_table(HERE / "results.csv", rows)
    (HERE / "publication.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: report[k] for k in ["status_counts", "termination_counts",
          "audited_target_hits", "worker_total_s", "elapsed_to_final_summary_s", "ipopt_points"]}))


if __name__ == "__main__":
    main()
