"""Verify both archives and select normal infrastructure retries; never solve."""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import types
import zipfile
from collections import Counter

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent
ORIGINAL = "grid_gdp_run_20261008_210901_dw5vq37s"
RETRY = "grid_gdp_retry_all_20261009_153057_czhvd9w7"


def archive(name):
    path = RESULTS / "archives" / (name + ".zip")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == Path(str(path) + ".sha256").read_text().split()[0]
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        manifest = dict((n.lstrip("*"), h) for h, n in (
            line.split(maxsplit=1) for line in z.read(name + "/SHA256SUMS").decode().splitlines()))
        assert set(z.namelist()) == {name + "/" + n for n in manifest} | {name + "/SHA256SUMS"}
        files = {n: z.read(name + "/" + n) for n in manifest}
    assert all(hashlib.sha256(files[n]).hexdigest() == h for n, h in manifest.items())
    return files, {"archive": "archives/" + name + ".zip", "sha256": digest,
                   "verified_member_hashes": len(manifest)}


def table(content):
    return list(csv.DictReader(io.StringIO(content.decode())))


def write_table(path, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    original, original_info = archive(ORIGINAL)
    retry, retry_info = archive(RETRY)
    for path in (HERE / "raw").iterdir():
        assert path.read_bytes() == retry[path.name]
    old_run = json.loads(original["run.json"])
    new_run = json.loads(retry["run.json"])
    assert new_run["retry_of"]["source_run_json_sha256"] == hashlib.sha256(original["run.json"]).hexdigest()
    assert new_run["runtime"] == old_run["runtime"]
    changes = {n for n in set(old_run["source_sha256"]) | set(new_run["source_sha256"])
               if old_run["source_sha256"].get(n) != new_run["source_sha256"].get(n)}
    assert changes <= {"grid_gdp_benchmark.py", "docs/grid_gdp_benchmark.md"}
    points = table(original["point_timings.csv"])
    assert len(points) == 20181
    assert (RESULTS / "grid_gdp_20261009/raw/point_timings.csv").read_bytes() == original["point_timings.csv"]

    # Use the archived analytic formula, independent of the current checkout.
    grid = types.ModuleType("archived_grid")
    grid.__file__ = str(HERE / "archived/gdp_models/grid.py")
    exec(compile(original["source/gdp_models/grid.py"], grid.__file__, "exec"), grid.__dict__)
    templates = {n: grid.build_grid_gdp(n, verify_csv=False) for n in grid.GRID_NAMES}
    references = {
        n: {(int(r["x"]), int(r["y"])): float(r["z_norm"])
            for r in table(original[f"source/benchmark_grids/{n}.csv"])}
        for n in grid.GRID_NAMES
    }

    def audited(row, files, source):
        row = dict(row)
        prefix = f"benchmark/{row['grid_name']}/{row['method']}/"
        record = json.loads(files[prefix + "result.json"])
        assert row["status"] == record["status"] and row["terminal_verified"] == "True"
        row.update(source_archive=source + ".zip", source_result=prefix + "result.json",
                   source_result_sha256=hashlib.sha256(files[prefix + "result.json"]).hexdigest())
        solution = files.get(prefix + "solution.json")
        row.update(audited_feasible=False, audited_target_hit=False)
        if solution is None:
            assert row["status"] == "unsupported_expression"
            return row
        solution = json.loads(solution)
        m = templates[row["grid_name"]].clone()
        for name, value in solution["variables"].items():
            v = m.find_component(name)
            assert v is not None and math.isfinite(value)
            v.set_value(value, skip_validation=True)
            assert v.lb is None or value >= v.lb - 1e-5
            assert v.ub is None or value <= v.ub + 1e-5
            if v.is_binary():
                assert abs(value - round(value)) <= 1e-5
        choices = [[i for i in m.I if grid.pyo.value(c[i].binary_indicator_var) > .5]
                   for c in (m.Xchoice, m.Ychoice)]
        assert all(len(c) == 1 for c in choices)
        point = tuple(c[0] for c in choices)
        fixed = grid.fix_grid_point(templates[row["grid_name"]].clone(), point)
        for v in fixed.component_data_objects(grid.pyo.Var):
            if v.name in solution["variables"]:
                assert abs(grid.pyo.value(v) - solution["variables"][v.name]) <= 1e-5
        value = float(grid.pyo.value(fixed.obj))
        assert abs(value - solution["objective"]) <= 1e-6
        reference = references[row["grid_name"]]
        assert abs(value - reference[point]) <= 1e-12
        gap = value - min(reference.values())
        row.update(audited_feasible=True, audited_point=json.dumps(point),
                   audited_objective=value, audited_gap=gap, audited_target_hit=gap <= 1e-5)
        return row

    old = [audited(r, original, ORIGINAL) for r in table(original["benchmark.csv"])]
    new = [audited(r, retry, RETRY) for r in table(retry["benchmark.csv"])]
    assert len(old) == 105 and len(new) == 21
    replacements = {(r["grid_name"], r["method"]): r for r in new if r["status"] == "finished"}
    assert len(replacements) == 11
    current = []
    for row in old:
        key = (row["grid_name"], row["method"])
        if key in replacements:
            assert row["status"] == "error"
            log = original[f"benchmark/{key[0]}/{key[1]}/run.log"].decode()
            assert "network session" in log and "Curl error:" in log
            row = replacements[key]
        current.append(row)
    write_table(HERE / "retry_audited.csv", new)
    write_table(HERE / "retry_target_hits.csv", [r for r in new if r["status"] == "finished" and r["audited_target_hit"]])
    write_table(HERE / "benchmark_current.csv", current)
    report = {
        "archives": [original_info, retry_info],
        "policy": "Replace only the 11 original GAMS network-session errors with their one normally terminated retry. Retain original records for repeated errors; retain every retry in retry_audited.csv and the original archive. No best-time or best-objective selection.",
        "point_data": "grid_gdp_20261009/raw/point_timings.csv",
        "point_data_sha256": hashlib.sha256(original["point_timings.csv"]).hexdigest(),
        "ipopt_points": len(points), "new_point_measurements": 0,
        "retry_status_counts": dict(Counter(r["status"] for r in new)),
        "retry_normal_target_hits": sum(r["status"] == "finished" and r["audited_target_hit"] for r in new),
        "retry_errors": [{k: r[k] for k in ("grid_name", "method", "message")} for r in new if r["status"] == "error"],
        "current_status_counts": dict(Counter(r["status"] for r in current)),
        "current_gdpopt_target_hits": sum(r["method"] in {"ric", "gloa", "loa"} and r["audited_target_hit"] for r in current),
        "current_gdpopt_cases": 63,
        "retry_worker_total_s": math.fsum(float(r["worker_wall_s"]) for r in new),
        "certificate_note": "Audited target hits validate saved feasible coordinates against the analytic expression and CSV minimum; they do not promote solver bounds to global certificates. Original target_hit fields are unchanged.",
    }
    (HERE / "publication.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: report[k] for k in ("retry_status_counts", "retry_normal_target_hits", "current_status_counts", "current_gdpopt_target_hits", "ipopt_points")}))


if __name__ == "__main__":
    main()
