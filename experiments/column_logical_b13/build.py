"""Freeze Column inputs and archived optimizers; never solve the process model."""

import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

from common import (
    METHODS,
    POINTS,
    csvwrite,
    events,
    measure,
    read,
    require,
    rows,
    sha,
    table,
    validate_plan,
    write,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
NAMES = {
    "original": "ipopt_dfo_non_cstr_20261015_172428_o671edu_.zip",
    "bam": "ipopt_dfo_non_cstr_20261015_223138_r3ifrgaq.zip",
    "review": "review_comparison_20261020_124949_return_1792527395393579314.zip",
}


def put(root, name, data):
    path = root / name
    require(path.resolve().is_relative_to(root.resolve()), "Unsafe destination")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class Archive:
    def __init__(self, name, checksum):
        self.path = REPO / "results/archives" / name
        require(sha(self.path) == checksum, "Archive hash mismatch: " + name)
        self.z = zipfile.ZipFile(self.path)
        require(self.z.testzip() is None, "ZIP CRC failure")
        names = self.z.namelist()
        self.prefix = names[0].split("/")[0] + "/"
        require(
            len(names) == len(set(names))
            and all(
                n.startswith(self.prefix) and ".." not in Path(n).parts for n in names
            ),
            "Ambiguous ZIP",
        )
        self.names = [n[len(self.prefix) :] for n in names if not n.endswith("/")]
        self.checks = {}
        if "SHA256SUMS" in self.names:
            self.checks = {
                n.lstrip("*"): h
                for h, n in (
                    line.split(maxsplit=1)
                    for line in self.get("SHA256SUMS").decode().splitlines()
                )
            }
        self.info = dict(
            path=str(self.path.relative_to(REPO)), sha256=checksum, root=self.prefix
        )

    def get(self, name):
        data = self.z.read(self.prefix + name)
        if name in self.checks:
            require(
                hashlib.sha256(data).hexdigest() == self.checks[name],
                "Member hash mismatch: " + name,
            )
        return data

    def json(self, name):
        return json.loads(self.get(name))


def audit_logic(evidence, output):
    import pyomo.environ as pyo

    def load(path, functions=None):
        text = (evidence / path).read_text()
        tree = ast.parse(text)
        if functions:
            tree.body = [
                n
                for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name in functions
            ]
            require(
                {n.name for n in tree.body} == set(functions), "Missing pinned helper"
            )
        else:
            tree.body = [
                n
                for n in tree.body
                if not (
                    isinstance(n, ast.ImportFrom)
                    and n.module == "pyomo.contrib.gdpopt.data_class"
                )
            ]
        scope = dict(
            __name__="_column_logic_only",
            __file__=str(evidence / path),
            pe=pyo,
            pyo=pyo,
        )
        exec(compile(tree, str(evidence / path), "exec"), scope)
        return scope

    with (
        patch(
            "pyomo.environ.SolverFactory",
            side_effect=AssertionError("No process solve permitted"),
        ),
        patch(
            "pyomo.opt.base.solvers.SolverFactory",
            side_effect=AssertionError("No process solve permitted"),
        ),
    ):
        model = load("column/gdp/column/gdp_column.py.txt")["build_column"](
            min_trays=8, max_trays=17, xD=0.95, xB=0.95
        )
        helpers = load(
            "column/gdp/dsda/dsda_functions.py.txt", ["get_external_information"]
        )
        mapping, count, lower, upper = helpers["get_external_information"](
            model, {model.YB: model.intTrays, model.YR: model.intTrays}
        )
        require(
            count == 2
            and list(lower.values()) == [1, 1]
            and list(upper.values()) == [15, 15],
            "External mapping differs",
        )
        require(
            mapping[1]["Boolean_vars_names"] == [f"YR[{i}]" for i in range(2, 17)]
            and mapping[2]["Boolean_vars_names"] == [f"YB[{i}]" for i in range(2, 17)]
            and model.feed_tray == 9,
            "Feed/external coordinate mapping differs",
        )
        logic = load("column/main_column.py.txt", ["problem_logic_column"])[
            "problem_logic_column"
        ]
        fixed = {
            v.name: pyo.value(v)
            for v in model.component_data_objects(pyo.BooleanVar)
            if v.fixed
        }
        outcomes = []
        for x in range(1, 16):
            for y in range(1, 16):
                for k in model.intTrays:
                    model.YR[k].set_value(k == x + 1)
                    model.YB[k].set_value(k == y + 1)
                valid = True
                for expression, variable in logic(model):
                    value = pyo.value(expression)
                    if variable.name in fixed:
                        valid = valid and value == fixed[variable.name]
                    else:
                        variable.set_value(value)
                for k in model.conditional_trays:
                    model.YP[k].set_value(pyo.value(model.tray[k].indicator_var))
                valid = valid and all(
                    pyo.value(c.body)
                    for c in model.component_data_objects(
                        pyo.LogicalConstraint, active=True
                    )
                )
                require(
                    valid == ((x, y) in POINTS),
                    "Pinned model logic disagrees with requested domain",
                )
                outcomes.append(
                    dict(
                        x1=x,
                        x2=y,
                        reflux_tray=x + 1,
                        boilup_tray=y + 1,
                        logical_allowed=bool(valid),
                    )
                )
    scope = {}
    exec(
        compile((REPO / "gdp_models/domains.py").read_text(), "domains.py", "exec"),
        scope,
    )
    require(
        set(map(tuple, scope["enumeration_plan"]("column")["points"])) == POINTS,
        "domains.py differs",
    )
    csvwrite(output / "logic_all_225.csv", outcomes)
    write(
        output / "logic_verification.json",
        dict(
            physical_feed_tray=9,
            external_feed_coordinate=8,
            external_order=["YR (reflux)", "YB (boilup)"],
            full_external_box=225,
            logical_allowed=64,
            old_search_box=81,
            excluded_old_search_coordinates=17,
            process_nlp_calls=0,
            rule="x1 >= 8 and x2 <= 8",
            algebraic_minimum_tray_constraints="Retained in original IPOPT acceptance; no feasibility filtering",
        ),
    )


def build(output):
    require(not output.exists(), "Do not overwrite an existing experiment package")
    output.mkdir(parents=True)
    integration = read(
        REPO / "results/process_ipopt_bam_v2_20261015/integration/manifest.json"
    )
    review_manifest = read(REPO / "results/review_comparison_20261020/manifest.json")
    checks = {
        d["archive"].split("/")[-1]: d["archive_sha256"]
        for d in integration["datasets"]
    }
    checks[NAMES["review"]] = review_manifest["return_archive"]["sha256"]
    archives = {k: Archive(n, checks[n]) for k, n in NAMES.items()}
    original, review = archives["original"], archives["review"]
    # Preserve and run the original 3,430-slot input audit without modifying its guard.
    with tempfile.TemporaryDirectory(prefix="column-original-audit-") as temporary:
        prior = Path(temporary)
        for name in review.names:
            if name.startswith("reproduction/"):
                put(prior, name[13:], review.get(name))
        sys.path.insert(0, str(REPO))
        from review_comparison.runner import check_inputs

        audited = check_inputs(prior)
        require(
            audited["planned_jobs"] == 3430 and not audited["missing_costs"],
            "Historical audit failed",
        )
        write(output / "provenance/original_3430_input_audit.json", audited)
    for group, archive, prefix in [
        ("original", original, "reproduction/"),
        ("bam", archives["bam"], "reproduction/"),
        ("review", review, "reproduction/frozen/non_cstr/"),
    ]:
        for name in archive.names:
            if name.startswith(prefix):
                rel = name[len(prefix) :]
                if (
                    rel.endswith(".py") or rel.startswith("fmqa_benchmark/vendor/")
                ) and not rel.startswith(("inputs/", "evidence/")):
                    put(output, f"frozen/{group}/" + rel, archive.get(name))
    for name in ("worker.py", "common.py", "__init__.py"):
        put(
            output,
            "frozen/sampling/review_comparison/" + name,
            review.get("reproduction/review_comparison/" + name),
        )
    for name in original.names:
        prefix = "reproduction/evidence/"
        if name.startswith(prefix) and (
            "/column/" in name or name.endswith(("/models.py.txt", "/domains.py.txt"))
        ):
            put(
                output, "provenance/evidence/" + name[len(prefix) :], original.get(name)
            )
    provenance = original.json("reproduction/inputs/column/provenance.json")
    for name, checksum in provenance["upstream"]["files_sha256"].items():
        require(
            sha(output / "provenance/evidence/column" / (name + ".txt")) == checksum,
            "Pinned model source changed",
        )
    audit_logic(output / "provenance/evidence", output / "provenance")
    for name in ("manifest.json", "provenance.json", "evaluations.csv", "summary.json"):
        put(
            output,
            "provenance/original_column/" + name,
            original.get("reproduction/inputs/column/" + name),
        )
    cost_path = (
        REPO / "results/process_ipopt_bam_v2_20261015/tables/cost_table_column.csv"
    )
    require(
        cost_path.read_bytes() == review.get("reproduction/data/cost_table_column.csv"),
        "Current cost table differs from executed representative input",
    )
    put(output, "inputs/column_81_original.csv", cost_path.read_bytes())
    costs = table(cost_path)
    require(
        len(costs) == 81
        and set(costs) == {(x, y) for x in range(7, 16) for y in range(1, 10)},
        "Original box is incomplete",
    )
    source = table(output / "provenance/original_column/evaluations.csv")
    require(
        set(source) == POINTS, "Original NLP table does not cover exact logical domain"
    )
    attempts = []
    for point, row in source.items():
        require(
            all(costs[point][k] == v for k, v in row.items()),
            "Objective/status/cost came from different rows",
        )
        rel = f"records/point_{int(row['point_index']):06d}.json"
        raw = original.get("reproduction/inputs/column/" + rel)
        require(
            hashlib.sha256(raw).hexdigest() == provenance["files_sha256"][rel],
            "Original point-record hash mismatch",
        )
        record = json.loads(raw)
        require(
            record["point"] == list(point)
            and record["accepted"] == (row["accepted"] == "True"),
            "Point identity/acceptance mismatch",
        )
        for k in (
            "objective",
            "candidate_objective",
            "total_wall_s",
            "setup_wall_s",
            "preprocess_wall_s",
            "solve_wall_s",
            "max_primal_violation",
        ):
            require(
                (float(row[k]) if row[k] else None) == record.get(k),
                "Same-attempt field mismatch: " + k,
            )
        for k in ("status", "termination", "solver", "initialization"):
            require(record.get(k, "") == row[k], "Same-attempt status mismatch: " + k)
        put(output, "provenance/original_column/" + rel, raw)
        attempts.append(
            dict(
                point=list(point),
                original_record=rel,
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    selected = [costs[p] for p in sorted(POINTS)]
    require(
        sum(r["accepted"] == "True" for r in costs.values())
        == sum(r["accepted"] == "True" for r in selected)
        == 29,
        "Accepted count requires investigation",
    )
    require(
        all(r["cost_source"] == "original" for r in selected),
        "A supplemented row entered the logical domain",
    )
    csvwrite(output / "inputs/column_64.csv", selected)
    target = min(
        float(r["objective"]) for r in costs.values() if r["accepted"] == "True"
    )
    require(
        float(costs[13, 4]["objective"]) == target, "Reference point/objective differs"
    )
    write(output / "provenance/point_attempts.json", attempts)
    publication = read(REPO / "results/cstr30_publication_20261025/manifest.json")
    for name, checksum in publication["input_sha256"].items():
        if "completed_runs.csv" in name or name.endswith("run_results.csv"):
            require(
                sha(REPO / name) == checksum, "Current publication input hash differs"
            )
    published_path = (
        REPO / "results/cstr30_publication_20261025/tables/primary_process_runs.csv"
    )
    require(
        sha(published_path)
        == publication["outputs_sha256"]["tables/primary_process_runs.csv"],
        "Current primary records changed",
    )
    published = [r for r in rows(published_path) if r["case"] == "column"]
    require(len(published) == 50, "Representative Column cohort is not 50 runs")
    csvwrite(output / "baseline/published_column_81_B16.csv", published)
    for name in (
        "manuscript/analysis_manifest_current.json",
        "results/cstr30_publication_20261025/manifest.json",
        "results/review_comparison_20261020/manifest.json",
        "results/process_ipopt_bam_v2_20261015/source_manifest.json",
        "results/process_ipopt_bam_v2_20261015/integration/manifest.json",
        "gdp_models/domains.py",
    ):
        put(output, "provenance/repository/" + name, (REPO / name).read_bytes())
    # Run the exact archived LHC generator in its original generation versions.
    generation = original.json("reproduction/build_provenance.json")[
        "initial_design_generation_versions"
    ]
    require(
        {n: importlib.metadata.version(n) for n in generation} == generation,
        "LHC generation environment differs",
    )
    scope = {}
    exec(
        compile(
            original.get("reproduction/case_studies/common.py"),
            "archived_lhc.py",
            "exec",
        ),
        scope,
    )
    generate = scope["generate_lhc_starting_points"]
    initial, plan, baseline = [], [], []
    for seed in range(10):
        starts = [list(p) for p in generate(2, 3, [8, 1], [15, 8], seed)]
        old_starts = [list(p) for p in generate(2, 3, [7, 1], [15, 9], seed)]
        initial.append(dict(seed=seed, starts=starts))
        for method in METHODS:
            group = (
                "review"
                if method in ("rbfopt", "uniform_without_replacement")
                else "bam"
                if method == "bam"
                else "original"
            )
            archive = archives[group]
            old_method = "rbfopt_msrsm_genetic" if method == "rbfopt" else method
            old_id = f"column_B16_seed{seed}_{old_method}"
            prefix = "jobs/" + old_id + "/"
            if group == "review":
                candidates = [
                    n[:-8]
                    for n in archive.names
                    if n.startswith(prefix) and n.endswith("/job.json")
                ]
                require(len(candidates) == 1, "Ambiguous representative attempt")
                prefix = candidates[0]
                old_job = archive.json(prefix + "job.json")
                spec = deepcopy(old_job["original_spec"])
                spec["method"] = method
                if method == "rbfopt":
                    spec["settings"]["global_search_method"] = "genetic"
                expected_runtime = archive.json(prefix + "runtime.json")
            else:
                old_job = None
                spec = archive.json(prefix + "spec.json")
                expected_runtime = archive.json(prefix + "runtime.json")
            require(
                spec["starts"] == old_starts
                and spec["budget"] == 16
                and spec["lower"] == [7, 1]
                and spec["upper"] == [15, 9],
                "Old design/protocol mismatch",
            )
            dest = output / "baseline/jobs" / old_id
            for name in archive.names:
                if name.startswith(prefix) and "/" not in name[len(prefix) :]:
                    put(dest, name[len(prefix) :], archive.get(name))
            result = read(dest / "result.json")
            ev = events(dest / "callbacks.jsonl")
            metric, _ = measure(spec, ev, result, costs, target)
            pub = next(
                r
                for r in published
                if r["method"] == old_method and int(r["seed"]) == seed
            )
            require(
                metric["category"] == pub["category"]
                and metric["target_hit"] == (pub["hit"] == "True"),
                "Historical outcome does not match current publication",
            )
            require(
                abs(metric["completion_s"] - float(pub["total_s"])) < 1e-8,
                "Historical timing reconstruction differs",
            )
            baseline.append(
                dict(method=method, seed=seed, budget=16, domain_size=81, **metric)
            )
            spec.update(
                job_id=f"column_logical_B13_seed{seed}_{method}",
                budget=13,
                lower=[8, 1],
                upper=[15, 8],
                starts=starts,
            )
            settings = (
                read(dest / "actual_settings.json")
                if (dest / "actual_settings.json").exists()
                else None
            )
            expected = deepcopy(settings)
            if method == "rbfopt":
                expected["max_evaluations"] = 13
            elif method == "dsda":
                expected["max_points_explored"] = 10
            elif method == "bam":
                expected["options"].update(
                    max_evals=10,
                    x_evaluated=starts,
                    f_evaluated=[
                        float(costs[tuple(p)]["objective"])
                        if costs[tuple(p)]["accepted"] == "True"
                        else None
                        for p in starts
                    ],
                )
            config = archive.json("run.json")["config"]
            job = dict(
                spec=spec,
                frozen=group,
                cpu=2,
                hard_seconds=2100,
                target=target,
                python=expected_runtime["executable"],
                reference_runtime=expected_runtime,
                reference_settings=settings,
                expected_settings=expected,
                config=config,
                baseline_job=old_id,
                baseline_archive=archive.info,
                baseline_member=prefix,
            )
            if method == "uniform_without_replacement":
                job["sampling_job"] = {
                    **old_job,
                    "budget": 13,
                    "lower": [8, 1],
                    "upper": [15, 8],
                    "starts": starts,
                }
            plan.append(job)
    validate_plan(plan)
    csvwrite(output / "baseline/runs.csv", baseline)
    write(output / "baseline/runs.json", baseline)
    write(output / "initial_designs.json", initial)
    write(output / "plan.json", plan)
    write(
        output / "input_verification.json",
        dict(
            original_points=81,
            selected_points=64,
            accepted_before=29,
            accepted_after=29,
            retained_unaccepted=35,
            excluded_structural_points=17,
            same_attempt_records_verified=64,
            reference_point=[13, 4],
            reference_objective=target,
            target_tolerance="1e-5*max(1,abs(reference))",
            lhc_generation_versions=generation,
            old_lhc_designs_reproduced=10,
            process_nlp_calls=0,
            old_budget=16,
            new_budget=13,
            scaled_budget_before_rounding=16 * 64 / 81,
            maximum_callbacks=650,
            methods=METHODS,
            planned_jobs=50,
        ),
    )
    for path in HERE.iterdir():
        if path.is_file() and path.suffix in (".py", ".sh", ".md"):
            put(output, path.name, path.read_bytes())
    files = {
        p.relative_to(output).as_posix(): sha(p)
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    write(
        output / "manifest.json",
        dict(
            schema=1,
            experiment="column-logical-64-B13",
            repository="SECQUOIA/Black-Box-for-GDP",
            source_base_revision=subprocess.check_output(
                ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
            ).strip(),
            remote_main_revision_at_preparation="2d1e2e49158d924f1fe589a55f7d7f210bf5f28b",
            uncommitted_followup_source=True,
            source_revision_note="No commit or push requested; exact new source bytes are hashed.",
            original_provider_revision=review_manifest["execution_provider_revision"],
            archives={k: a.info for k, a in archives.items()},
            files_sha256=files,
            permitted_factors=[
                "Column domain 81 to 64",
                "budget 16 to 13",
                "new common LHC designs within new domain",
            ],
            original_process_nlp_calls=0,
            target=target,
            cpu=2,
        ),
    )
    checksums = {**files, "manifest.json": sha(output / "manifest.json")}
    (output / "SHA256SUMS").write_text(
        "".join(f"{h}  {n}\n" for n, h in sorted(checksums.items()))
    )
    print(json.dumps(read(output / "input_verification.json"), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output.resolve())
