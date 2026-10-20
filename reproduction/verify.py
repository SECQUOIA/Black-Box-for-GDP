"""Independent numerical and provenance checks; never load a solver."""

from collections import Counter
import csv
import io
import json
import math
import statistics
import zipfile

from common import DATA, GRID, PROCESS, ROOT, read_json, rows, sha
from tables import interval, restart_cost


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(a, b, message, tol=1e-12):
    require(math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol), message)


def verify(tables):
    provenance = read_json(ROOT / "reproduction/provenance.json")
    for r in provenance["imports"]:
        if "sha256" in r:
            require(
                sha(ROOT / r["path"]) == r["sha256"],
                f"Imported evidence changed: {r['path']}",
            )
    support = DATA / "supporting_data"
    process, grid = rows(PROCESS / "run_results.csv"), rows(GRID / "runs.csv")
    require(len(process) == 560 and len(grid) == 4200, "Run count")
    categories = Counter(r["category"] for r in process)
    require(
        categories
        == {"target_reached": 291, "target_not_reached": 268, "execution_failed": 1},
        "Process outcomes",
    )
    require(sum(int(r["total_evals"]) for r in grid) == 201833, "Grid callbacks")
    bam = [r for r in process if r["method"] == "bam"]
    require(
        len(bam) == 140 and sum(int(r["within_budget_callbacks"]) for r in bam) == 3430,
        "BAM selection/callbacks",
    )
    for item in read_json(ROOT / "reproduction/cited_files.json")["files"]:
        require(
            sha(ROOT / item["path"]) == item["sha256"],
            f"Cited file changed: {item['path']}",
        )
    protocol_count = 0
    metadata_cache = {}
    for method in ("dsda", "rbfopt", "bam", "fmqa_sa"):
        for job in read_json(support / f"protocol_{method}.json")["jobs"]:
            source = job["source"]
            if source not in metadata_cache:
                metadata_cache[source] = {
                    r["job_id"]: r for r in read_json(ROOT / source)
                }
            original = metadata_cache[source][job["job_id"]]
            require(original["spec"] == job["spec"], "Protocol job spec differs")
            settings = dict(original["settings"])
            # The supplied manuscript protocol intentionally shortens these two
            # absolute Dantzig executable paths. Original metadata is unchanged.
            for key in ("minlp_solver_path", "nlp_solver_path"):
                if key in settings:
                    settings[key] = str(settings[key]).rsplit("/", 1)[-1]
            require(settings == job["actual_settings"], "Protocol settings differ")
            protocol_count += 1
    require(protocol_count == 560, "Protocol job count")
    expected = {
        (r["scope"], r["case"], int(r["budget"]), r["method"]): r
        for r in rows(support / "success_intervals.csv")
    }
    actual = tables["supp_08"] + sum((tables[f"supp_{i:02}"] for i in range(9, 14)), [])
    require(len(expected) == len(actual) == 476, "Interval groups")
    for r in actual:
        e = expected[r["scope"], r["case"], r["budget"], r["method"]]
        for k in ("n", "hits", "p_hat", "ci95_lower", "ci95_upper"):
            close(r[k], e[k], f"Interval {k}: {r}")
    for r in rows(support / "interval_key.csv"):
        lo, hi = interval(int(r["hits"]), int(r["n"]))
        close(lo, r["ci95_lower"], "Interval key lower")
        close(hi, r["ci95_upper"], "Interval key upper")
    groups = {
        (r["case"], int(r["budget"]), r["method"]): r
        for r in rows(PROCESS / "group_summary.csv")
    }
    for r in tables["main_07"]:
        e = groups[r["case"], r["budget"], r["method"]]
        close(r["median_completion_s"], e["median_reconstructed_s"], "Process median")
        close(r["tts99_s"], e["tts99_s"], "Process TTS99")
    for e in rows(GRID / "tts99_summary.csv"):
        rr = [
            r
            for r in grid
            if r["grid_name"] == e["grid_name"]
            and r["method"] == e["method"]
            and r["max_evals"] == e["max_evals"]
        ]
        hits = sum(r["target_hit"] == "True" for r in rr)
        close(
            restart_cost(hits, [float(r["estimated_total_s"]) for r in rr]),
            e["tts99_s"],
            "Grid TTS99",
        )
    stopping = read_json(support / "stopping_diagnostics.json")
    for path, digest in stopping["source_sha256"].items():
        require(sha(ROOT / path) == digest, f"Stopping source hash: {path}")
    selected = {r["job_id"]: r for r in process + grid}
    for r in stopping["runs"]:
        e = selected[r["job_id"]]
        callbacks = int(
            e["within_budget_callbacks"]
            if r["family"] == "Process"
            else e["total_evals"]
        )
        require(callbacks == r["callbacks"], f"Stopping callback count: {r['job_id']}")
        hit = (
            e["category"] == "target_reached"
            if r["family"] == "Process"
            else e["target_hit"] == "True"
        )
        require(hit == r["target_hit"], f"Stopping target: {r['job_id']}")
        if hit:
            first = int(
                e["first_hit_callback"]
                if r["family"] == "Process"
                else e["first_hit_evaluation"]
            )
            require(
                first == r["first_target_callback"]
                and callbacks - first == r["callbacks_after_first_target"],
                "Post-target callback accounting",
            )
    pooled = {r["key"]: r for r in stopping["summary"]}
    for r in tables["supp_04"]:
        for k in (
            "runs",
            "stop_counts",
            "callbacks_total",
            "target_hits",
            "post_target_median_successful",
        ):
            require(r[k] == pooled[r["key"]][k], f"Stopping pooled {k}")
    recovery = read_json(support / "terminal_callback_recovery.json")
    require(len(recovery["runs"]) == 14, "Terminal-only count")
    for source in recovery["sources"]:
        require(
            sha(ROOT / source["archive"]) == source["sha256"], "Recovery archive hash"
        )
        require(
            sha(ROOT / source["runner_package"]) == source["runner_package_sha256"],
            "Recovery runner hash",
        )
    for r in recovery["runs"]:
        with zipfile.ZipFile(ROOT / r["archive"]) as archive:
            callbacks = [
                json.loads(line)
                for line in archive.read(r["callback_member"]).splitlines()
            ]
            summary = list(
                csv.DictReader(io.StringIO(archive.read(r["summary_member"]).decode()))
            )
            e = next(x for x in summary if x["job_id"] == r["job_id"])
            # Archive schema is preserved; validate the terminal record and wrapper summary.
            last = callbacks[-1]
            require(
                last["point"] == r["terminal_point"], f"Terminal point: {r['job_id']}"
            )
            close(
                last["raw_objective"],
                r["terminal_accepted_objective"],
                "Terminal objective",
            )
            require(
                r["terminal_point"] == r["wrapper_best_point"], "Terminal wrapper point"
            )
            close(
                r["terminal_accepted_objective"],
                r["wrapper_best_accepted_objective"],
                "Terminal wrapper objective",
            )
            require(e["category"] == "target_reached", "Recovered wrapper category")
    audit = DATA / "algebraic_audit"
    for line in (audit / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(None, 1)
        require(
            sha(audit / name.lstrip("* ")) == digest, f"Algebraic input hash {name}"
        )
    for r in tables["supp_14"]:
        for typ in ("result", "solution"):
            require(
                sha(audit / r[f"{typ}_local_path"]) == r[f"{typ}_sha256"],
                "Saved vector/result hash",
            )
        require(
            float(r["original_model_max_violation"]) <= 1e-5, "Saved feasibility report"
        )
    require(
        sum(r["uniform_bound_conflict"] for r in tables["supp_14"]) == 11,
        "Uniform conflict count",
    )
    old = {
        (r["instance_id"], r["method"]): r
        for r in rows(audit / "table8_bound_audit.csv")
    }
    for r in tables["supp_14"]:
        require(
            r["uniform_bound_conflict"]
            == (old[r["instance_id"], r["method"]]["uniform_bound_conflict"] == "True"),
            "Audit classification",
        )
    for r in tables["main_01"]:
        cost = rows(PROCESS / f"cost_table_{r['case']}.csv")
        require(
            all(
                math.isfinite(float(c["total_wall_s"])) and float(c["total_wall_s"]) > 0
                for c in cost
            ),
            "Point timing completeness",
        )
    require(
        sum(r["measured_coordinates"] for r in tables["main_01"]) == 2455,
        "Point inventory",
    )
    require(
        sum(r["finite_lookup"] for r in tables["main_01"]) == 1260, "Accepted inventory"
    )
    return {
        "process_runs": 560,
        "process_categories": dict(categories),
        "grid_runs": 4200,
        "grid_callbacks": 201833,
        "bam_runs": 140,
        "bam_callbacks": 3430,
        "interval_groups": 476,
        "terminal_only_records": 14,
        "stopping_run_records": 4760,
        "bound_conflicts": 11,
        "measured_process_coordinates": 2455,
        "accepted_process_coordinates": 1260,
        "relative_and_absolute_numeric_tolerance": 1e-12,
        "historical_feasibility_tolerance": 1e-5,
        "new_optimization_or_nlp_runs": 0,
        "saved_feasibility_recheck": "Historical report verified; use --replay for fresh saved-vector evaluation.",
    }


def verify_figure8(path):
    actual = read_json(path)
    expected = read_json(DATA / "figure8_reference.json")
    require(
        actual["points"] == expected["points"],
        "Figure 8 points/categories/markers changed",
    )
    groups = {}
    for r in actual["points"]:
        groups.setdefault((r["case"], r["budget"], r["method"]), []).append(
            r["completion_s"]
        )
    return {
        "points": len(actual["points"]),
        "groups": len(groups),
        "execution_failures": sum(r["marker"] == "s" for r in actual["points"]),
        "medians": {
            "/".join(map(str, k)): statistics.median(v) for k, v in groups.items()
        },
        "point_records_identical_to_supplied_manifest": True,
    }


def verify_replays(output):
    """Compare official replay tables numerically without overwriting retained data."""
    compared = []
    for rel, baseline in [
        ("grid_replay/runs.csv", GRID / "runs.csv"),
        ("grid_replay/tts99_summary.csv", GRID / "tts99_summary.csv"),
        ("grid_replay/budget_summary.csv", GRID / "budget_summary.csv"),
        ("grid_replay/gdp_runs.csv", GRID / "gdp_runs.csv"),
        (
            "algebraic_replay/comparison.csv",
            ROOT / "results/gdp_comparison_current/analysis/comparison.csv",
        ),
    ]:
        actual, expected = rows(output / rel), rows(baseline)
        require(len(actual) == len(expected), f"Replay row count: {rel}")
        numeric_differences = 0
        for a, e in zip(actual, expected):
            require(a.keys() == e.keys(), f"Replay schema: {rel}")
            for k in a:
                if a[k] == e[k]:
                    continue
                try:
                    close(a[k], e[k], f"Replay cell: {rel} {k}")
                except (TypeError, ValueError):
                    raise ValueError(
                        f"Replay differs: {rel} {k}: {a[k]!r} vs {e[k]!r}"
                    ) from None
                numeric_differences += 1
        compared.append(
            {
                "path": rel,
                "rows": len(actual),
                "numeric_format_or_rounding_differences": numeric_differences,
            }
        )
    return compared
