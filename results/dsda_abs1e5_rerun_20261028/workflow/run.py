"""Execute only D-SDA against sealed stored responses, then pair every seed."""

import argparse
from collections import Counter
from contextlib import redirect_stdout
import csv
from datetime import datetime, timezone
import hashlib
import importlib.abc
import importlib.metadata
import importlib.util
import itertools
import json
import math
import os
from pathlib import Path
import platform
import random
import signal
import subprocess
import sys
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parent
THREADS = {
    k: "1"
    for k in (
        "OMP_NUM_THREADS",
        "OMP_THREAD_LIMIT",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "GOTO_NUM_THREADS",
        "NUMEXPR_MAX_THREADS",
    )
}
THREADS.update(
    OMP_DYNAMIC="FALSE",
    MKL_DYNAMIC="FALSE",
    CUDA_VISIBLE_DEVICES="",
    PYTHONNOUSERSITE="1",
)
os.environ.update(THREADS)


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=2, allow_nan=False) + "\n")


def table(p):
    with Path(p).open() as f:
        return list(csv.DictReader(f))


def csvwrite(p, rows):
    rows = list(rows)
    if not rows:
        return
    with Path(p).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def key(spec):
    return (spec["scope"], spec["case"], int(spec["budget"]), int(spec["seed"]))


def truth(v):
    return v is True or v == "True"


def nullable_number(v):
    if v is None or v == "":
        return None
    n = float(v)
    return n if math.isfinite(n) else None


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def verify_repository(repo):
    """Identify the project by retained Git history, including renamed forks."""
    repo = Path(repo).resolve()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True
        )

    top = git("rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.strip()).resolve() != repo:
        raise ValueError("Expected an existing repository root: " + str(repo))
    head = git("rev-parse", "HEAD")
    if head.returncode:
        raise ValueError("Cannot read repository HEAD")
    anchor = "eeb560059c7001ad82c13b9249168531af073f95"
    ancestry = git("merge-base", "--is-ancestor", anchor, "HEAD")
    if ancestry.returncode:
        raise ValueError(
            "Repository does not contain the adopted Grid execution revision in its HEAD history: "
            + anchor
        )
    frozen = git("show", anchor + ":grid_dsda.py")
    expected = "7873a2344eb9b40e9bc3f35354448494e9d8230d0879377e8934fa2cc517a77a"
    if (
        frozen.returncode
        or hashlib.sha256(frozen.stdout.encode()).hexdigest() != expected
    ):
        raise ValueError("Repository historical D-SDA source fingerprint mismatch")
    remotes = {}
    names = git("remote")
    if names.returncode:
        raise ValueError("Cannot inspect repository remotes")
    from urllib.parse import urlsplit, urlunsplit

    for name in names.stdout.splitlines():
        value = git("remote", "get-url", name)
        if value.returncode:
            raise ValueError("Cannot inspect remote " + name)
        url = value.stdout.strip()
        if "://" in url:
            parsed = urlsplit(url)
            # Credentials are not needed for repository identity or provenance.
            host = parsed.hostname or ""
            if parsed.port:
                host += ":" + str(parsed.port)
            url = urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        remotes[name] = url
    return dict(
        repository=str(repo),
        head=head.stdout.strip(),
        remotes=remotes,
        verified_ancestor=anchor,
        verified_ancestor_dsda_sha256=expected,
        rule="Exact retained execution commit is an ancestor of HEAD and its D-SDA source hash matches; remote URLs are recorded, not required to use the latest repository name.",
    )


def pin_shared_cpu():
    """User-authorized shared execution on exactly one permitted logical CPU."""
    allowed = sorted(os.sched_getaffinity(0))
    if not allowed:
        raise RuntimeError("No CPU is permitted by the current affinity")
    selected = 2 if 2 in allowed else allowed[0]
    os.sched_setaffinity(0, {selected})
    effective = sorted(os.sched_getaffinity(0))
    if effective != [selected]:
        raise RuntimeError("Failed to pin exactly one CPU")
    return dict(
        cpu=selected,
        allowed_before_pin=allowed,
        effective_cpus=effective,
        execution_mode="shared_cpu_explicitly_requested_by_user",
        requires_idle_cpu=False,
        occupancy_wait_seconds=0,
        affinity_note="One logical CPU, one numerical-library thread, sequential jobs; other workloads may share the same CPU.",
        timing_caveat="Concurrent server load confounds search wall-time comparisons with the historical runs.",
    )


def allocate_idle_cpu():
    """Use the launcher's fresh observation or measure immediately before launch."""
    selection_path = os.environ.get("DSDA_CPU_SELECTION_RECORD")
    if selection_path:
        source = Path(selection_path).resolve()
        if source != (ROOT / "CPU_SELECTION.json").resolve():
            raise ValueError("CPU selection must belong to this sealed input snapshot")
        selection = read(source)
        expected = read(ROOT / "SHA256SUMS.json").get("CPU_SELECTION.json")
        if not expected or sha(source) != expected:
            raise ValueError("CPU selection record hash mismatch")
        measured = datetime.fromisoformat(selection["rounds"][-1]["utc"])
        age = (datetime.now(timezone.utc) - measured).total_seconds()
        if not 0 <= age <= 60:
            raise RuntimeError(
                "CPU observation is stale; use launch.py to measure again"
            )
    else:
        from select_dsda_cpu import select

        selection = select(preferred=-1)
    if selection["selected_cpu"] is None or not selection.get(
        "physical_core_observed_idle"
    ):
        raise RuntimeError(
            "No fully idle physical core observed; D-SDA was not started"
        )
    selected = selection["selected_cpu"]
    if selected not in os.sched_getaffinity(0):
        raise RuntimeError("Selected CPU is outside the current permitted affinity")
    os.sched_setaffinity(0, {selected})
    effective = sorted(os.sched_getaffinity(0))
    if effective != [selected]:
        raise RuntimeError("Could not pin the selected CPU")
    return dict(
        cpu=selected,
        effective_cpus=effective,
        selection=selection,
        execution_mode="observed_idle_physical_core_then_pinned",
        exclusive_reservation=False,
        note="The sampled SMT pair was idle before launch; affinity does not exclude future competing tasks.",
    )


def verify_package():
    expected = read(ROOT / "SHA256SUMS.json")
    for name, digest in expected.items():
        if sha(ROOT / name) != digest:
            raise ValueError("Package SHA256 mismatch: " + name)
    jobs = read(ROOT / "inputs/jobs.json")
    keys = [key(j["spec"]) for j in jobs]
    assert len(keys) == len(set(keys)) == 1190
    assert Counter(k[0] for k in keys) == {"grid": 1050, "process": 140}
    for job in jobs:
        s = job["spec"]
        old = job["baseline"]
        ev = job["baseline_events"]
        assert key(s) == (
            old["scope"],
            old["case"],
            int(old["budget"]),
            int(old["seed"]),
        )
        assert s["method"] == "dsda" and s["settings"] == dict(
            diagonal=True, tie_break="first", tol=1e-12
        )
        assert len(ev) == int(old["evaluations"]) <= s["budget"]
        assert [e["point"] for e in ev[:3]] == s["starts"]
        if s["scope"] == "process":
            full = table(ROOT / f"inputs/process/{s['case']}_full.csv")
            points = [tuple(json.loads(r["point"])) for r in full]
            domain = set(
                itertools.product(
                    *(range(lo, hi + 1) for lo, hi in zip(s["lower"], s["upper"]))
                )
            )
            assert len(points) == len(set(points)) and set(points) == domain
            assert all(
                r["accepted"] in ("True", "False")
                and r["status"] not in ("", "pending")
                for r in full
            )
            assert all(
                math.isfinite(float(r["objective"]))
                if r["accepted"] == "True"
                else not r["objective"]
                for r in full
            )
            lookup = {
                tuple(json.loads(r["point"])): r
                for r in table(ROOT / f"inputs/process/{s['case']}_oracle.csv")
            }
            for row in full:
                point = tuple(json.loads(row["point"]))
                if point in lookup:
                    assert row["accepted"] == lookup[point]["accepted"]
                    assert row["objective"] == lookup[point]["objective"]
                else:
                    assert s["case"] == "dynamic" and row["accepted"] == "False"
                    assert point[0] >= point[1] and point != (9, 9)
            assert job["hard_seconds"] == 2100
    return jobs


BLOCKED = []


class SolverBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {
            "pyomo",
            "gams",
            "pyscipopt",
            "gdp",
            "gdp_models",
            "rbfopt",
            "bam",
            "fmqa_benchmark",
            "case_studies",
            "cyipopt",
        }:
            BLOCKED.append("import:" + fullname)
            raise RuntimeError(
                "Solver/model/other-method import prohibited: " + fullname
            )


def install_no_solver_guard():
    if any(isinstance(f, SolverBlocker) for f in sys.meta_path):
        return
    sys.meta_path.insert(0, SolverBlocker())

    def audit(event, args):
        if event in {
            "subprocess.Popen",
            "os.system",
            "os.posix_spawn",
            "os.exec",
            "os.fork",
            "os.forkpty",
        }:
            BLOCKED.append(event)
            raise RuntimeError(
                "Child process creation prohibited inside lookup worker: " + event
            )

    sys.addaudithook(audit)


def execute(job, out, improvement=1e-5):
    """The only experimental change is the extra improvement keyword."""
    import numpy as np

    # Load numerical runtime before installing the solver guard.
    importlib.import_module("pandas")
    importlib.import_module("scipy")
    import grid_dsda as dsda
    from adopted_analysis import hit

    install_no_solver_guard()
    out.mkdir(parents=True, exist_ok=False)
    s = job["spec"]
    random.seed(s["seed"])
    np.random.seed(s["seed"])
    events = []
    algorithm = None
    error = None
    status = "completed"
    partial = None
    started = time.perf_counter()
    original_dsda = dsda.dsda_from_csv
    original_tracker = dsda.TrackedObjective
    try:
        with (out / "search.log").open("w") as log, redirect_stdout(log):
            if s["scope"] == "grid":

                class Recording(original_tracker):
                    def __call__(self, p):
                        v = super().__call__(p)
                        events.append(
                            dict(
                                index=self.call_count,
                                point=list(p),
                                raw_objective=v,
                                accepted=True,
                                lookup_wall_s=self.wall_times[-1],
                                phase="initial" if self.call_count <= 3 else "adaptive",
                            )
                        )
                        return v

                dsda.TrackedObjective = Recording
                algorithm = dsda.run_dsda_from_best_starting_points(
                    ROOT / f"inputs/grids/{s['case']}.csv",
                    s["starts"],
                    target_value=job["target"],
                    verbose=True,
                    max_points_explored=s["budget"],
                    improvement_abs_tol=improvement,
                    **s["settings"],
                )
            else:
                core = module(
                    "frozen_" + job["cohort"], ROOT / "frozen" / f"{job['cohort']}.py"
                )
                raw = table(ROOT / f"inputs/process/{s['case']}_oracle.csv")
                full = {
                    tuple(json.loads(r["point"])): r
                    for r in table(ROOT / f"inputs/process/{s['case']}_full.csv")
                }
                lookup = {
                    tuple(json.loads(r["point"])): {**r, "csv_line": i}
                    for i, r in enumerate(raw, 2)
                }

                class StrictOracle(core.Oracle):
                    def __call__(self, p):
                        point = tuple(int(round(float(x))) for x in p)
                        if point not in full:
                            raise core.MissingEvaluation(
                                f"Missing stored objective/status for {point}; no fallback"
                            )
                        stored = full[point]
                        if point not in lookup and (
                            stored["accepted"] != "False"
                            or core.logical_allowed(s["case"], point)
                        ):
                            raise core.MissingEvaluation(
                                f"Missing historical response for {point}"
                            )
                        return super().__call__(p)

                oracle = StrictOracle(s, lookup, out)
                events = oracle.events

                def with_tolerance(*args, **kwargs):
                    return original_dsda(
                        *args, improvement_abs_tol=improvement, **kwargs
                    )

                dsda.dsda_from_csv = with_tolerance

                # Retain partial movement state when the historical terminal callback
                # raises before the search function can return its result.
                def capture(frame, event, arg):
                    nonlocal partial
                    frame.f_trace_lines = False
                    if event == "exception" and frame.f_code is original_dsda.__code__:
                        if isinstance(arg[1], core.BudgetStop):
                            partial = {
                                name: frame.f_locals.get(name)
                                for name in (
                                    "path",
                                    "history",
                                    "current",
                                    "current_val",
                                    "best_seen_point",
                                    "best_seen_value",
                                    "major_iter",
                                )
                            }
                    return capture if frame.f_code is original_dsda.__code__ else None

                sys.settrace(capture)
                try:
                    algorithm = core.optimize(s, oracle, {}, out)
                except core.BudgetStop:
                    status = "budget_completed"
                finally:
                    sys.settrace(None)
    except Exception as exc:
        status = (
            "missing_lookup"
            if type(exc).__name__ == "MissingEvaluation"
            else "execution_failed"
        )
        error = traceback.format_exc()
    finally:
        dsda.dsda_from_csv = original_dsda
        dsda.TrackedObjective = original_tracker
    elapsed = time.perf_counter() - started
    assert len(events) <= s["budget"]
    assert [e["point"] for e in events[:3]] == s["starts"][: len(events[:3])]
    accepted = [e for e in events if e["accepted"]]
    best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
    success = bool(
        best
        and hit(best["raw_objective"], job["target"])
        and status in ("completed", "budget_completed")
    )
    if s["scope"] == "grid" and algorithm:
        reason = algorithm["stop_reason"] or (
            "target_value"
            if algorithm["runs"]
            and math.isclose(
                algorithm["runs"][-1]["best_value"],
                job["target"],
                abs_tol=s["settings"]["tol"],
                rel_tol=0,
            )
            else "all_ranked_starts_exhausted"
        )
        movement = [r["path"] for r in algorithm["runs"]]
        endpoint = movement[-1][-1] if movement else None
    else:
        reason = (
            "budget_stop"
            if status == "budget_completed"
            else (
                "no_improving_neighbor"
                if algorithm and not algorithm["stop_reason"]
                else status
            )
        )
        movement = (
            algorithm["path"] if algorithm else partial["path"] if partial else None
        )
        endpoint = movement[-1] if movement else None
    result = dict(
        spec=s,
        improvement_abs_tol=improvement,
        status=status,
        error=error,
        category="execution_failed"
        if status not in ("completed", "budget_completed") or best is None
        else "target_reached"
        if success
        else "target_not_reached",
        hit=success,
        best_objective=best["raw_objective"] if best else None,
        best_point=best["point"] if best else None,
        evaluations=len(events),
        first_hit=next(
            (e["index"] for e in accepted if hit(e["raw_objective"], job["target"])),
            None,
        )
        if success
        else None,
        termination=reason,
        endpoint=endpoint,
        last_callback=events[-1]["point"] if events else None,
        search_s=elapsed,
        lookup_s=sum(e["lookup_wall_s"] for e in events),
        path=movement,
        algorithm_result=algorithm,
        partial_algorithm_state=partial,
        process_nlp_calls=0,
        blocked_solver_or_process_attempts=list(BLOCKED),
        effective_cpus=sorted(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else None,
    )
    write(out / "result.json", result)
    if s["scope"] == "grid":
        with (out / "callbacks.jsonl").open("w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
    write(
        out / "settings.json",
        dict(original=s, delta={"improvement_abs_tol": improvement}),
    )
    return result, events


def verify_legacy(jobs, out):
    report = []
    for i, j in enumerate(jobs):
        r, ev = execute(j, out / j["spec"]["job_id"], None)
        old = j["baseline"]
        oe = j["baseline_events"]
        assert [e["point"] for e in ev] == [e["point"] for e in oe], (
            "legacy coordinates",
            key(j["spec"]),
        )
        assert [e["accepted"] for e in ev] == [e["accepted"] for e in oe]
        assert [e["raw_objective"] for e in ev] == [e["raw_objective"] for e in oe], (
            "legacy values",
            key(j["spec"]),
        )
        assert r["evaluations"] == int(old["evaluations"])
        assert r["best_objective"] == nullable_number(old["best_objective"]), (
            key(j["spec"]),
            r["best_objective"],
            old["best_objective"],
        )
        assert r["hit"] == truth(old["hit"]) and r["category"] == old["category"]
        assert r["first_hit"] == nullable_number(old["first_hit"]), (
            key(j["spec"]),
            r["first_hit"],
            old["first_hit"],
        )
        report.append(
            dict(
                key=key(j["spec"]),
                exact_callbacks=True,
                exact_outcome=True,
                termination=r["termination"],
                path=r["path"],
                endpoint=r["endpoint"],
            )
        )
        if (i + 1) % 100 == 0:
            print("Verified legacy", i + 1, flush=True)
    write(
        out / "verification.json",
        dict(count=len(report), runs=report, process_nlp_calls=0),
    )


def summarize(jobs, out):
    pairs = []
    missing = []
    legacy = (
        read(ROOT / "validation/legacy/verification.json")
        if (ROOT / "validation/legacy/verification.json").exists()
        else None
    )
    replay = {tuple(r["key"]): r for r in legacy["runs"]} if legacy else {}
    for j in jobs:
        s = j["spec"]
        p = out / "runs" / s["job_id"] / "result.json"
        old = j["baseline"]
        if not p.exists():
            missing.append(s["job_id"])
            r = {}
        else:
            r = read(p)
            assert r["spec"] == s
        oe = j["baseline_events"]
        le = replay.get(key(s), {})
        callbacks = out / "runs" / s["job_id"] / "callbacks.jsonl"
        ne = (
            [json.loads(line) for line in callbacks.read_text().splitlines()]
            if callbacks.exists()
            else []
        )
        oldhit = truth(old["hit"])
        newhit = r.get("hit", False)
        pairs.append(
            dict(
                scope=s["scope"],
                case=s["case"],
                budget=s["budget"],
                seed=s["seed"],
                old_hit=oldhit,
                new_hit=newhit,
                old_category=old["category"],
                new_category=r.get("category", "missing"),
                old_best_objective=old["best_objective"],
                new_best_objective=r.get("best_objective"),
                old_callbacks=int(old["evaluations"]),
                new_callbacks=r.get("evaluations", 0),
                callback_delta=r.get("evaluations", 0) - int(old["evaluations"]),
                old_first_hit=nullable_number(old["first_hit"]),
                new_first_hit=r.get("first_hit"),
                old_termination=j["baseline_termination"],
                old_reproduced_termination=le.get("termination"),
                new_termination=r.get("termination"),
                old_last_callback=json.dumps(oe[-1]["point"]),
                new_last_callback=json.dumps(r.get("last_callback")),
                old_endpoint=json.dumps(le.get("endpoint")),
                new_endpoint=json.dumps(r.get("endpoint")),
                callback_path_changed=[e["point"] for e in oe]
                != [e["point"] for e in ne],
                endpoint_changed=le.get("endpoint") != r.get("endpoint")
                if le
                else None,
                last_callback_changed=oe[-1]["point"] != r.get("last_callback"),
                old_search_s=old["search_s"],
                new_search_s=r.get("search_s"),
                new_lookup_s=r.get("lookup_s"),
                old_only=oldhit and not newhit,
                new_only=newhit and not oldhit,
                old_path=json.dumps(le.get("path")),
                new_path=json.dumps(r.get("path")),
                new_status=r.get("status", "missing"),
            )
        )
    assert (
        len(pairs)
        == len({(r["scope"], r["case"], r["budget"], r["seed"]) for r in pairs})
        == 1190
    )
    csvwrite(out / "paired_comparison.csv", pairs)

    def group_summary(group, label):
        return dict(
            **label,
            runs=len(group),
            old_hits=sum(r["old_hit"] for r in group),
            new_hits=sum(r["new_hit"] for r in group),
            hit_delta=sum(r["new_hit"] - r["old_hit"] for r in group),
            old_only=sum(r["old_only"] for r in group),
            new_only=sum(r["new_only"] for r in group),
            old_callbacks=sum(r["old_callbacks"] for r in group),
            new_callbacks=sum(r["new_callbacks"] for r in group),
            changed_callback_counts=sum(r["callback_delta"] != 0 for r in group),
            changed_callback_paths=sum(r["callback_path_changed"] for r in group),
            changed_last_callbacks=sum(r["last_callback_changed"] for r in group),
            changed_endpoints=sum(r["endpoint_changed"] is True for r in group),
            failures=sum(
                r["new_status"] not in ("completed", "budget_completed") for r in group
            ),
        )

    grids = [
        group_summary(
            [r for r in pairs if r["scope"] == "grid" and r["budget"] == b],
            dict(budget=b),
        )
        for b in [10, 30, 50, 70, 100]
    ]
    conditions = sorted(
        {(r["case"], r["budget"]) for r in pairs if r["scope"] == "process"}
    )
    process = [
        group_summary(
            [
                r
                for r in pairs
                if r["scope"] == "process" and (r["case"], r["budget"]) == (c, b)
            ],
            dict(case=c, budget=b),
        )
        for c, b in conditions
    ]
    totals = [
        group_summary([r for r in pairs if r["scope"] == scope], dict(scope=scope))
        for scope in ["grid", "process"]
    ]
    totals.append(
        group_summary(
            [r for r in pairs if r["case"].startswith("cstr_")], dict(scope="cstr")
        )
    )
    csvwrite(out / "grid_budget_summary.csv", grids)
    csvwrite(out / "process_condition_summary.csv", process)
    csvwrite(out / "descriptive_totals.csv", totals)
    other = table(ROOT / "inputs/adopted_all_methods.csv")
    comparisons = []
    for scope, c, b in [("grid", "all", b) for b in [10, 30, 50, 70, 100]] + [
        ("process", c, b) for c, b in conditions
    ]:
        ds = [
            r
            for r in pairs
            if r["scope"] == scope
            and r["budget"] == b
            and (c == "all" or r["case"] == c)
        ]
        for method in sorted({r["method"] for r in other if r["method"] != "dsda"}):
            rows = [
                r
                for r in other
                if r["scope"] == scope
                and int(r["budget"]) == b
                and r["method"] == method
                and (c == "all" or r["case"] == c)
            ]
            if not rows:
                continue
            assert len(rows) == len(ds)
            hits = sum(truth(r["hit"]) for r in rows)
            oh = sum(r["old_hit"] for r in ds)
            nh = sum(r["new_hit"] for r in ds)

            def relation(a):
                return "more" if a > hits else "fewer" if a < hits else "equal"

            comparisons.append(
                dict(
                    scope=scope,
                    case=c,
                    budget=b,
                    method=method,
                    runs=len(rows),
                    unchanged_other_hits=hits,
                    old_dsda_hits=oh,
                    new_dsda_hits=nh,
                    old_relation=relation(oh),
                    new_relation=relation(nh),
                    relation_changed=relation(oh) != relation(nh),
                )
            )
    csvwrite(out / "unchanged_method_comparison.csv", comparisons)
    failed = sum(
        r["new_status"] not in ("completed", "budget_completed", "missing")
        for r in pairs
    )
    summary = dict(
        expected=1190,
        completed=1190 - len(missing) - failed,
        failed=failed,
        missing=len(missing),
        missing_jobs=missing,
        totals=totals,
        method_hit_order_changes=[r for r in comparisons if r["relation_changed"]],
        process_nlp_calls=0,
    )
    write(out / "summary.json", summary)
    lines = [
        "# D-SDA 절대 개선 허용오차 변경 실험",
        "",
        "이 결과는 별도 민감도 실험이며 원고 대표 결과로 자동 채택하지 않는다.",
        "원래 LD-SDA 구현 전체를 재현한 실험이 아니다.",
        "이웃 탐색, 방향 탐색 및 이에 연결된 best_seen와 다중 시작점 best_run 갱신은 엄격한 old_value - new_value > 1e-5를 사용한다.",
        "실제 관측 최솟값 incumbent와 결과 성공 판정은 기존대로 모든 callback을 사용한다.",
        "동률 판단과 Grid 목표값 종료는 기존 tol=1e-12이며 상대 개선 기준은 없다.",
        "Process 미수용 응답은 1e6이고 마지막 callback은 기존대로 기록한 뒤 예산 종료 예외를 발생시킨다.",
        "기존 공통 성공 판정 함수를 그대로 가져와 최선 목적값과 목표값의 절대 차이가 1e-5 * max(1, abs(target)) 이하인지 판정한다.",
        "반복 평가를 포함한 모든 callback을 예산에 계산하며 초기 세 점의 순서와 시작점 선택을 유지한다.",
        "Grid에는 원래 watchdog 제한이 없고 Process에는 실행별 2100초 watchdog을 유지한다.",
        "기존 종료 사유가 명시적으로 남지 않은 Grid 기록은 원본 callback 경로와 일치한 기본 설정 검증 실행의 종료 사유를 별도 열에 보관한다.",
        "legacy 경로 열은 보관된 callback과 완전히 일치하는 기본 설정 재실행으로 얻었으며 원본 기록으로 가장하지 않는다.",
        "새 탐색 시간에는 기록과 부분 경로 추적 비용이 포함되므로 기존 시간 대비 순수 성능 향상으로 해석하지 않는다.",
        f"예상 실행은 1190건이며 완료 {summary['completed']}건, 실패 {failed}건, 누락 {len(missing)}건이다.",
        "추가 NLP 호출은 0건이며 worker의 solver import 및 하위 프로세스 생성 차단 내역을 각 result.json에 보관한다.",
    ]
    for t in totals:
        lines.append(
            f"{t['scope']} 목표 도달은 {t['old_hits']}/{t['runs']}에서 {t['new_hits']}/{t['runs']}로 바뀌었으며 기존에만 성공 {t['old_only']}쌍과 새 실행에서만 성공 {t['new_only']}쌍이다."
        )
    lines += [
        "다른 방법은 재실행하지 않았으며 목표 도달 횟수에 따른 비교 변화는 unchanged_method_comparison.csv에 기록한다.",
        "실행 직전에 SMT 쌍의 사용률을 측정해 비어 있던 물리 코어를 선택하고 논리 CPU 하나에 고정하며 수치 라이브러리는 1스레드로 제한한다.",
        "CPU 선택은 독점 예약이 아니므로 이후 부하 변화와 기록 비용을 포함한 시간 차이를 허용오차 변경의 속도 효과로 해석하지 않는다.",
        "실행 명령과 환경은 execution_manifest.json에 있고 입력 및 소스 해시는 reproduction/SHA256SUMS.json에 있다.",
    ]
    (out / "README.md").write_text("\n".join(lines) + "\n")
    return summary


def server_run(repo, output=None):
    jobs = verify_package()
    if platform.system() != "Linux" or not platform.node().startswith("dantzig"):
        raise RuntimeError("Full experiment requires Dantzig Linux")
    repo = repo.resolve()
    if str(repo) != "/local/scratch/a/lee4382/repository/RBFopt_Test":
        raise ValueError("Unexpected Dantzig repository")
    identity = verify_repository(repo)
    expected_python = repo / ".venv-dantzig/bin/python"
    if Path(sys.executable).absolute() != expected_python:
        raise ValueError("Use existing .venv-dantzig/bin/python")
    versions = {n: importlib.metadata.version(n) for n in ("numpy", "scipy", "pandas")}
    if platform.python_version() != "3.11.16" or versions != {
        "numpy": "2.4.6",
        "scipy": "1.17.1",
        "pandas": "2.3.3",
    }:
        raise RuntimeError("Historical environment mismatch: " + str(versions))
    now = datetime.now(timezone.utc)
    out = (
        Path(output).resolve()
        if output
        else repo
        / "results"
        / ("dsda_abs1e5_" + now.strftime("%Y%m%d_%H%M%S") + "_" + str(os.getpid()))
    )
    if not out.is_relative_to(repo / "results"):
        raise ValueError(
            "Experiment output must remain inside the repository results directory"
        )
    if out.with_suffix(".zip").exists():
        raise FileExistsError(
            "Result archive already exists: " + str(out.with_suffix(".zip"))
        )
    out.mkdir(exist_ok=False)
    env = dict(
        command=sys.argv,
        utc_started=now.isoformat(),
        repository=str(repo),
        repository_identity=identity,
        server_revision=subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip(),
        server_worktree_status=subprocess.check_output(
            ["git", "-C", str(repo), "status", "--short"], text=True
        ),
        python=platform.python_version(),
        executable=sys.executable,
        platform=platform.platform(),
        host=platform.node(),
        versions=versions,
        threads=THREADS,
        source_manifest=read(ROOT / "manifest.json"),
        process_nlp_calls=0,
    )
    write(out / "execution_manifest.json", env)
    allocation = allocate_idle_cpu()
    for name in ("stat", "loadavg"):
        try:
            allocation["proc_" + name] = Path("/proc", name).read_text()
        except OSError as error:
            allocation["proc_" + name + "_read_error"] = str(error)
    write(out / "cpu_allocation.json", allocation)
    env["effective_cpus"] = allocation["effective_cpus"]
    env["cpu_allocation"] = allocation
    print(
        "SELECTED CPU",
        allocation["cpu"],
        "threads=1; physical core observed idle before launch",
        flush=True,
    )
    write(out / "execution_manifest.json", env)
    print("RESULTS", out, flush=True)
    # Source remains in the immutable input directory; archive it with results.
    import shutil

    shutil.copytree(
        ROOT, out / "reproduction", ignore=shutil.ignore_patterns("__pycache__")
    )
    subprocess.run(
        [sys.executable, str(ROOT / "test_experiment.py")],
        check=True,
        stdout=(out / "unit_tests.log").open("w"),
        stderr=subprocess.STDOUT,
    )
    smoke = [
        next(j for j in jobs if j["spec"]["scope"] == "grid"),
        next(j for j in jobs if j["spec"]["case"] == "cstr_30"),
        next(j for j in jobs if j["spec"]["case"] == "column"),
    ]
    for j in smoke:
        dest = out / "smoke" / j["spec"]["job_id"]
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "run.py"),
                "worker",
                "--job",
                j["spec"]["job_id"],
                "--output",
                str(dest),
            ],
            check=True,
            timeout=j["hard_seconds"],
        )
        if read(dest / "result.json")["status"] not in (
            "completed",
            "budget_completed",
        ):
            raise RuntimeError("Smoke failed: " + str(dest))
    for i, j in enumerate(jobs):
        dest = out / "runs" / j["spec"]["job_id"]
        dest.parent.mkdir(exist_ok=True)
        command = [
            sys.executable,
            str(ROOT / "run.py"),
            "worker",
            "--job",
            j["spec"]["job_id"],
            "--output",
            str(dest),
        ]
        started = time.perf_counter()
        child = subprocess.Popen(command, start_new_session=True)
        try:
            code = child.wait(timeout=j["hard_seconds"])
            timeout = False
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            code = child.returncode
        if not (dest / "result.json").exists():
            dest.mkdir(exist_ok=True)
            callbacks = dest / "callbacks.jsonl"
            ev = (
                [json.loads(line) for line in callbacks.read_text().splitlines()]
                if callbacks.exists()
                else []
            )
            accepted = [e for e in ev if e["accepted"]]
            best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
            write(
                dest / "result.json",
                dict(
                    spec=j["spec"],
                    status="execution_failed",
                    category="execution_failed",
                    hit=False,
                    error=f"worker_exit={code}; timeout={timeout}",
                    evaluations=len(ev),
                    best_objective=best["raw_objective"] if best else None,
                    last_callback=ev[-1]["point"] if ev else None,
                    termination="watchdog_timeout" if timeout else "worker_exit",
                    process_nlp_calls=0,
                ),
            )
        write(
            dest / "process.json",
            dict(
                command=command,
                returncode=code,
                watchdog_seconds=j["hard_seconds"],
                watchdog_timeout=timeout,
                wall_s=time.perf_counter() - started,
            ),
        )
        result = read(dest / "result.json")
        if result["status"] == "missing_lookup":
            print("STOP: missing lookup", j["spec"]["job_id"], flush=True)
            break
        if (i + 1) % 25 == 0:
            print("Completed", i + 1, "/", len(jobs), flush=True)
    summary = summarize(jobs, out)
    env.update(utc_finished=datetime.now(timezone.utc).isoformat(), summary=summary)
    write(out / "execution_manifest.json", env)
    hashes = {
        str(p.relative_to(out)): sha(p)
        for p in sorted(out.rglob("*"))
        if p.is_file() and p.name != "OUTPUT_SHA256SUMS.json"
    }
    write(out / "OUTPUT_SHA256SUMS.json", hashes)
    archive = out.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                z.write(p, str(Path(out.name) / p.relative_to(out)))
    print("RETURN_ARCHIVE", archive, flush=True)
    print("SCP_RETURN_ARCHIVE", archive, flush=True)
    print("SHA256", sha(archive), flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "mode", choices=["verify", "legacy", "smoke", "worker", "server", "analyze"]
    )
    p.add_argument("--output", type=Path)
    p.add_argument("--job")
    p.add_argument("--repo", type=Path)
    p.add_argument(
        "--input",
        type=Path,
        help="Sealed prepared input directory inside the repository",
    )
    args = p.parse_args()
    if args.input:
        ROOT = args.input.resolve()
        sys.path.insert(0, str(ROOT))
    if args.mode == "worker":
        job = next(
            j
            for j in read(ROOT / "inputs/jobs.json")
            if j["spec"]["job_id"] == args.job
        )
        result, _ = execute(job, args.output)
        if result["status"] not in ("completed", "budget_completed"):
            sys.exit(1)
    elif args.mode == "server":
        server_run(args.repo, args.output)
    elif args.mode == "analyze":
        print(summarize(verify_package(), args.output))
    else:
        jobs = verify_package()
        if args.mode == "verify":
            print("Verified sealed inputs for 1190 runs; no missing domain responses")
        elif args.mode == "legacy":
            verify_legacy(jobs, args.output)
        else:
            chosen = [next(j for j in jobs if j["spec"]["scope"] == "grid")] + [
                next(j for j in jobs if j["spec"]["case"] == c)
                for c in ["cstr_5", "cstr_30", "column", "dynamic", "small_batch"]
            ]
            results = []
            for j in chosen:
                result, _ = execute(j, args.output / j["spec"]["job_id"])
                results.append(result)
                assert result["status"] in ("completed", "budget_completed"), result[
                    "error"
                ]
            write(
                args.output / "smoke_summary.json",
                dict(
                    count=len(results),
                    jobs=[
                        dict(
                            job=r["spec"]["job_id"],
                            status=r["status"],
                            callbacks=r["evaluations"],
                        )
                        for r in results
                    ],
                    process_nlp_calls=0,
                ),
            )
