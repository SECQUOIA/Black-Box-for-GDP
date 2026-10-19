"""Counting-oracle regression tests; never invoke an optimizer other than DSDA."""

import contextlib
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from case_studies.dsda_domain import box_membership, rank_observed_starts
from grid_dsda import dsda_from_csv, get_neighbors
from instrumentation import TrackedObjective
from evaluation_trace import ACTIVE_TRACE, finite_value


class MembershipOnly(dict):
    def __getitem__(self, key):
        raise AssertionError("Uncharged dictionary value access")

    def get(self, *args):
        raise AssertionError("Uncharged dictionary value access")

    def values(self):
        raise AssertionError("Uncharged dictionary values access")

    def items(self):
        raise AssertionError("Uncharged dictionary items access")


class Collector:
    import time

    timer = staticmethod(time.perf_counter)

    def __init__(self):
        self.events = []

    def record(
        self, point, value, incumbent, elapsed, started, finished, exception_type=None
    ):
        self.events.append(
            {
                "point": [int(x) for x in point],
                "value": finite_value(value),
                "incumbent": finite_value(incumbent),
            }
        )


def search(lower, upper, start, oracle, budget=100, initial_value=None):
    tracked = TrackedObjective(oracle)
    result = dsda_from_csv(
        "",
        start,
        diagonal=True,
        verbose=False,
        max_points_explored=budget,
        grid=MembershipOnly(box_membership(lower, upper)),
        tracked_objective=tracked,
        start_value=initial_value,
    )
    return tracked, result


class FairnessTests(unittest.TestCase):
    def test_recovery_rejects_changed_search_sources_or_parent_archive(self):
        from process_dsda_fairness_recovery import check_sources, parent_inventory

        old = {"grid_dsda.py": "unchanged", "process_dsda_fairness.py": "old"}
        current = {**old, "process_dsda_fairness.py": "new",
                   "process_dsda_fairness_recovery.py": "new"}
        self.assertEqual(check_sources(old, current), ["process_dsda_fairness.py"])
        historical = {**old, "docs/process_dsda_fairness_report.txt": "old-report"}
        self.assertEqual(check_sources(historical, current), [
            "docs/process_dsda_fairness_report.txt", "process_dsda_fairness.py",
        ])
        with self.assertRaisesRegex(ValueError, "source inventory"):
            check_sources(historical, {k: v for k, v in current.items() if k != "grid_dsda.py"})
        with self.assertRaisesRegex(ValueError, "source inventory"):
            check_sources({**historical, "other_input.txt": "required"}, current)
        with self.assertRaisesRegex(ValueError, "search/model inputs"):
            check_sources(old, dict(current, **{"grid_dsda.py": "changed"}))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wrong.zip"
            p.write_bytes(b"not the verified parent")
            with self.assertRaisesRegex(ValueError, "parent hash differs"):
                parent_inventory(p)

    def test_recovery_rejects_development_runtime_as_server_measurement(self):
        from process_dsda_fairness_recovery import check_runtime

        parent = {"development_only": False, "host": "dantzig", "executable": "python",
                  "versions": {}, "thread_environment": {},
                  "affinity": {"effective_cpus": [7]}}
        check_runtime(dict(parent), parent, False)
        with self.assertRaisesRegex(ValueError, "same host"):
            check_runtime(dict(parent, development_only=True), parent, False)
        with self.assertRaisesRegex(ValueError, "original CPU"):
            check_runtime(dict(parent, affinity={"effective_cpus": [6]}), parent, False)

    def test_frozen_process_paths_do_not_use_pandas_or_regenerate_starts(self):
        import grid_dsda
        import case_studies.common
        from process_dsda_fairness import invoke, verify_plan, check_events
        from evaluation_trace import EvaluationTrace

        class ForbiddenPandas:
            def __getattr__(self, name):
                raise AssertionError(f"Unexpected pandas API in process DSDA: {name}")

        root = Path(__file__).resolve().parents[1]
        ref = json.loads(
            (
                root / "benchmark_protocols/process_dsda_fairness_reference.json"
            ).read_text()
        )
        with contextlib.ExitStack() as stack:
            trace_dir = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            stack.enter_context(patch.object(grid_dsda, "pd", ForbiddenPandas()))
            stack.enter_context(
                patch.object(
                    case_studies.common,
                    "generate_lhc_starting_points",
                    side_effect=AssertionError("Frozen starts must be used"),
                )
            )
            for case in ("column", "cstr", "dynamic"):
                stack.enter_context(
                    patch(
                        f"case_studies.{case}_dsda.generate_lhc_starting_points",
                        side_effect=AssertionError("Frozen starts must be used"),
                    )
                )
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            for spec in verify_plan(ref):
                with EvaluationTrace(trace_dir / "lookup.csv", spec) as trace:
                    out = invoke(spec)
                    check_events(spec, trace.events, out["result_record"])
                    trace.complete(out["result_record"])
                self.assertLessEqual(
                    out["result_record"]["total_evals"], spec["max_evaluations"]
                )

    def test_cstr_seed9_tolerance_and_invalid_return(self):
        from evaluation_trace import EvaluationTrace
        from process_dsda_fairness import ROOT, REFERENCE, read, invoke, check_events

        spec = next(s for s in read(ROOT / REFERENCE)["plan"]
                    if s["job_id"] == "cstr_15_B22_seed9_dsda")
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            with EvaluationTrace(Path(d) / "lookup.csv", spec) as trace:
                record = invoke(spec)["result_record"]
                checks = check_events(spec, trace.events, record)
                self.assertEqual(list(record["best_point"]), [5, 2])
                minimum = min(e["value"] for e in trace.events if e["value_kind"] == "finite")
                self.assertGreater(record["best_value"], minimum)
                self.assertLess(record["best_value"] - minimum, 1e-12)
                self.assertFalse(checks["target_hit"])
                # Even the strictly smaller observed value is not the actual
                # engine return. Do not blanket-accept any near-equal point.
                tampered = dict(record, best_point=[5, 1], best_value=minimum)
                with self.assertRaisesRegex(ValueError, "tolerance-aware"):
                    check_events(spec, trace.events, tampered)
                tampered = dict(record, best_value=record["best_value"] + 1e-13)
                with self.assertRaisesRegex(ValueError, "lookup response"):
                    check_events(spec, trace.events, tampered)

    def test_worker_retains_optimizer_return_when_validation_fails(self):
        import process_dsda_fairness as runner

        spec = next(s for s in runner.read(runner.ROOT / runner.REFERENCE)["plan"]
                    if s["job_id"] == "cstr_15_B22_seed9_dsda")
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            directory = Path(d)
            runner.save(directory / "run.json", {"source_files_sha256": {}, "plan": [spec]})
            with patch.object(runner, "hashes", return_value={}), patch.object(
                runner, "check_events", side_effect=ValueError("injected audit failure")
            ):
                with self.assertRaisesRegex(RuntimeError, "injected audit failure"):
                    runner.worker(directory, spec["job_id"])
            job = directory / "jobs" / spec["job_id"]
            result = runner.valid_job(job)
            saved = runner.read(job / "optimizer_return.json")
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["result_record"], saved["result_record"])
            self.assertGreater(result["result_record"]["wall_time_s"], 0)
            self.assertEqual(result["result_record"]["total_evals"], 22)

    def test_pandas_is_recorded_without_blocking_unused_api_version(self):
        import process_dsda_fairness as runner
        from unittest.mock import patch

        versions = {"numpy": "2.4.6", "scipy": "1.17.1", "pandas": "3.0.5"}
        with (
            patch.dict("os.environ", {k: "1" for k in runner.THREADS}),
            patch("cpu_affinity.pin_cpu", return_value=None),
            patch("cpu_affinity.affinity_record", return_value={}),
            patch.object(runner, "git_state", return_value={}),
            patch.object(
                runner.importlib.metadata, "version", side_effect=versions.__getitem__
            ),
        ):
            result = runner.runtime(None, True)
            self.assertEqual(result["versions"], versions)
            versions["numpy"] = "unexpected"
            with self.assertRaisesRegex(RuntimeError, "compatible DFO environment"):
                runner.runtime(None, True)

    def test_boundaries_zero_and_one(self):
        for lower in (0, 1):
            domain = MembershipOnly(
                box_membership([lower, lower], [lower + 2, lower + 2])
            )
            for x, y in domain:
                expected = sorted(
                    (a, b)
                    for a in range(lower, lower + 3)
                    for b in range(lower, lower + 3)
                    if (a, b) != (x, y) and max(abs(a - x), abs(b - y)) == 1
                )
                self.assertEqual(get_neighbors((x, y), domain, True), expected)
                tracked, r = search(
                    [lower, lower],
                    [lower + 2, lower + 2],
                    (x, y),
                    lambda p: 1.0,
                    initial_value=1.0,
                )
                self.assertEqual(tracked.evaluation_points, expected)
                self.assertEqual(r["point_evaluations"], len(expected))

    def test_hidden_nan_consumes_callback(self):
        calls = []

        def oracle(p):
            calls.append(p)
            return math.nan if p == (0, 1) else 1.0

        tracked, result = search([0, 0], [2, 2], (1, 1), oracle, initial_value=0.0)
        self.assertEqual(len(calls), 8)
        self.assertIn((0, 1), calls)
        self.assertEqual(tracked.call_count, 8)
        self.assertEqual(result["best_point"], (1, 1))

    def test_three_dimensional_box(self):
        expected = [
            (a, b, c)
            for a in (1, 2, 3)
            for b in (1, 2, 3)
            for c in (1, 2, 3)
            if (a, b, c) != (2, 2, 2)
        ]
        d = MembershipOnly(box_membership([1] * 3, [3] * 3))
        self.assertEqual(get_neighbors((2, 2, 2), d, True), expected)
        tracked, _ = search(
            [1] * 3, [3] * 3, (2, 2, 2), lambda p: math.nan, initial_value=0.0
        )
        self.assertEqual(tracked.evaluation_points, expected)
        self.assertEqual(tracked.call_count, 26)

    def test_initialization_and_mid_neighborhood_caps(self):
        from case_studies.column_dsda import run_column_dsda
        from case_studies import column_case

        starts = [(14, 4), (12, 1), (9, 8)]
        for cap in (3, 4, 6):
            with patch(
                "case_studies.column_dsda.generate_lhc_starting_points",
                side_effect=AssertionError("Must use frozen points"),
            ):
                out = run_column_dsda(starting_points=starts, max_evaluations=cap)
            self.assertEqual(out["tracked_evals"], cap)
            self.assertEqual(out["starting_points"], starts)
            if cap == 4:
                self.assertEqual(out["run_result"]["explored_points"][1][0], (13, 3))
            observed = out["starting_point_values"] + (
                out["run_result"]["explored_points"] if out["run_result"] else []
            )
            self.assertIn(tuple(out["best_point"]), [p[0] for p in observed])
            self.assertEqual(
                column_case.column_objective(out["best_point"]), out["best_value"]
            )
        with patch(
            "case_studies.column_dsda.column_objective",
            side_effect=AssertionError("No callback permitted"),
        ):
            with self.assertRaisesRegex(ValueError, "entire initial design"):
                run_column_dsda(starting_points=starts, max_evaluations=2)

    def test_line_search_unsuccessful_and_true_boundary(self):
        # Neighborhood: (0,), (2,); line trial (3,) must be charged before rejection.
        tr, r = search(
            [0],
            [4],
            (1,),
            lambda p: math.nan if p == (3,) else -float(p[0]),
            initial_value=-1.0,
        )
        self.assertEqual(tr.evaluation_points[:3], [(0,), (2,), (3,)])
        self.assertEqual(r["history"][1]["line_search_points"][-1][2], "rejected")
        tr, r = search([0], [3], (1,), lambda p: -float(p[0]), initial_value=-1.0)
        self.assertNotIn((4,), tr.evaluation_points)
        self.assertIn(
            ((4,), None, "out_of_bounds"), r["history"][1]["line_search_points"]
        )

    def test_mid_line_search_cap(self):
        tr, r = search(
            [0], [10], (1,), lambda p: -float(p[0]), budget=3, initial_value=-1.0
        )
        self.assertEqual(tr.evaluation_points, [(0,), (2,), (3,)])
        self.assertEqual(r["best_point"], (3,))
        self.assertEqual(r["stop_reason"], "max_points_explored")

    def test_repeated_initial_calls_and_start_value_reuse(self):
        tr = TrackedObjective(lambda p: float(p[0]))
        p, v, _, obs = rank_observed_starts([(1,), (1,), (2,)], tr)
        self.assertEqual(tr.call_count, 3)
        r = dsda_from_csv(
            "",
            p,
            grid=MembershipOnly(box_membership([0], [3])),
            tracked_objective=tr,
            start_value=v,
            max_points_explored=1,
            verbose=False,
        )
        self.assertEqual(tr.evaluation_points, [(1,), (1,), (2,), (0,)])
        self.assertEqual(r["point_evaluations"], 1)
        tr, r = search([0], [3], (1,), lambda p: -float(p[0]), initial_value=-1.0)
        self.assertGreater(tr.call_count, tr.unique_evaluation_count)

    def test_initial_selection_uses_observations_only(self):
        from case_studies.cstr_dsda import choose_best_feasible_start

        p, v, _, _ = choose_best_feasible_start(
            [(1, 2), (2, 1), (2, 2)],
            TrackedObjective(lambda p: sum(p)),
            MembershipOnly(),
        )
        self.assertEqual((p, v), ((1, 2), 3))
        tr = TrackedObjective(lambda p: math.inf)
        with self.assertRaisesRegex(ValueError, "all observed responses unsuccessful"):
            rank_observed_starts([(1,), (2,), (3,)], tr)
        self.assertEqual(tr.call_count, 3)

    def test_full_batch_archived_regression(self):
        from small_batch_full_domain import run_dfo

        root = Path(__file__).resolve().parents[1]
        ref = json.loads(
            (
                root / "benchmark_protocols/process_dsda_fairness_reference.json"
            ).read_text()
        )
        specs = [s for s in ref["plan"] if s["case_name"] == "small_batch"]
        self.assertEqual(len(specs), 10)
        for spec in specs:
            collector = Collector()
            token = ACTIVE_TRACE.set(collector)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    out = run_dfo(spec, {})
            finally:
                ACTIVE_TRACE.reset(token)
            old = ref["old_dsda"][spec["job_id"]]
            self.assertEqual(
                [e["point"] for e in collector.events],
                [e["point"] for e in old["events"]],
            )
            self.assertEqual(
                [e["value"] for e in collector.events],
                [(e["value"], e["value_kind"]) for e in old["events"]],
            )
            self.assertEqual(
                [e["incumbent"] for e in collector.events],
                [(e["incumbent"], e["incumbent_kind"]) for e in old["events"]],
            )
            for k in (
                "total_evals",
                "best_value",
                "best_point",
                "found_optimum",
                "initial_evals",
                "adaptive_evals",
            ):
                self.assertEqual(out["result_record"][k], old["record"][k])
            self.assertEqual(out["stop_reason"], old["stop_reason"])


if __name__ == "__main__":
    unittest.main()
