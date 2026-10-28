"""Grid-only semantic and negative-control tests before any full execution."""

from copy import deepcopy
import importlib.util
import inspect
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import grid_dsda as dsda
from adopted_analysis import hit
from protocol import (
    audit_one,
    read,
    validate_cohort,
    validate_job,
    verify_grid,
    without_times,
    write,
)

HERE = Path(__file__).resolve().parent


def load_baseline():
    spec = importlib.util.spec_from_file_location(
        "retained_grid_dsda", HERE / "baseline_source/grid_dsda.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic(module, grid, starts, budget=100, predicate=None, tie="first"):
    records = []
    tracker = module.TrackedObjective

    class Recording(tracker):
        def __call__(self, p):
            value = super().__call__(p)
            records.append((p, value))
            return value

    options = {"target_stop": predicate} if predicate is not None else {}
    with (
        patch.object(module, "load_grid_csv", return_value=(None, grid)),
        patch.object(module, "TrackedObjective", Recording),
    ):
        result = module.run_dsda_from_best_starting_points(
            "synthetic.csv",
            starts,
            diagonal=True,
            tie_break=tie,
            max_points_explored=budget,
            improvement_abs_tol=1e-5,
            verbose=False,
            **options,
        )
    return result, records


class GridTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = load_baseline()
        cls.jobs = read(HERE / "inputs/jobs.json")

    def test_success_boundary_uses_unrounded_values(self):
        self.assertTrue(hit(1e-5, 0.0))
        self.assertTrue(hit(math.nextafter(1e-5, 0.0), 0.0))
        self.assertFalse(hit(math.nextafter(1e-5, math.inf), 0.0))
        self.assertFalse(hit(None, 0.0))
        self.assertFalse(hit(float("nan"), 0.0))

    def test_nonzero_target_scale_and_actual_float_boundary(self):
        self.assertTrue(hit(2 + 1.5e-5, 2.0))
        self.assertFalse(hit(2 + 3e-5, 2.0))
        for target in (-2.0, 0.25, 2.0, 100.0):
            boundary = target + 1e-5 * max(1.0, abs(target))
            for v in (
                math.nextafter(boundary, -math.inf),
                boundary,
                math.nextafter(boundary, math.inf),
            ):
                self.assertEqual(
                    hit(v, target), abs(v - target) <= 1e-5 * max(1.0, abs(target))
                )

    def test_exact_improvement_boundary_and_descent_code_unchanged(self):
        self.assertFalse(dsda.improves(0.0, 1e-5, False, 1e-12, 1e-5))
        self.assertTrue(
            dsda.improves(0.0, math.nextafter(1e-5, math.inf), False, 1e-12, 1e-5)
        )
        self.assertFalse(dsda.improves(1e8 - 1e-6, 1e8, False, 1e-12, 1e-5))
        self.assertTrue(dsda.improves(1e8 - 1e-4, 1e8, False, 1e-12, 1e-5))
        for name in ("dsda_from_csv", "get_neighbors", "improves"):
            self.assertEqual(
                inspect.getsource(getattr(dsda, name)),
                inspect.getsource(getattr(self.baseline, name)),
            )

    def test_unaccepted_movement_observation_and_checkpoint_position(self):
        grid = {(-1, 0): 9e-6, (0, 0): 1.5e-5, (1, 0): 1.0, (3, 0): 2.0, (4, 0): 3.0}
        starts = [(0, 0), (3, 0), (4, 0)]
        new, ev = synthetic(dsda, grid, starts, predicate=hit)
        old, oev = synthetic(self.baseline, grid, starts)
        self.assertEqual(ev, oev[: len(ev)])
        self.assertEqual(new["runs"][0]["path"], [(0, 0)])
        self.assertEqual(new["best_value"], 1.5e-5)
        self.assertEqual(new["incumbent_trajectory"][-1], 9e-6)
        self.assertEqual(len(new["runs"]), 1)
        self.assertGreater(len(old["runs"]), 1)
        self.assertEqual(new["stop_reason"], "target_common_success")
        self.assertEqual(
            new["target_stop_checks"],
            [
                dict(
                    descent_index=1,
                    callback=5,
                    observed_incumbent=9e-6,
                    target=0.0,
                    reached=True,
                )
            ],
        )
        self.assertEqual(ev[3][1], 9e-6)
        self.assertEqual(len(ev), 5)  # No immediate stop at callback four.
        self.assertTrue(new["result_record"]["found_optimum"])

    def test_default_mode_preserves_full_baseline_and_tie_options(self):
        grid = {
            (x, y): float((x - 1) ** 2 + (y - 1) ** 2) + 0.1
            for x in range(4)
            for y in range(4)
        }
        for tie in ("first", "nearest", "farthest"):
            for budget in (3, 4, 10, 50):
                with self.subTest(tie=tie, budget=budget):
                    old, oev = synthetic(
                        self.baseline, grid, [(3, 3), (0, 0), (2, 3)], budget, tie=tie
                    )
                    new, nev = synthetic(
                        dsda, grid, [(3, 3), (0, 0), (2, 3)], budget, tie=tie
                    )
                    self.assertEqual(oev, nev)
                    self.assertEqual(without_times(old), without_times(new))

    def test_no_improvement_continues_ranked_starts_without_target_hit(self):
        grid = {(x, 0): 1.0 for x in range(6)}
        starts = [(1, 0), (3, 0), (5, 0)]
        new, ev = synthetic(dsda, grid, starts, predicate=hit)
        old, oev = synthetic(self.baseline, grid, starts)
        self.assertEqual(len(new["runs"]), 3)
        self.assertEqual(ev, oev)
        self.assertEqual([p for p, v in ev[:3]], starts)
        self.assertEqual(
            new["total_point_evaluations_including_initial_ranking"], len(ev)
        )
        self.assertGreater(len(ev), len(set(p for p, v in ev)))
        self.assertEqual(without_times(new["runs"]), without_times(old["runs"]))

    def test_budget_stop_precedes_target_checkpoint(self):
        grid = {(x, 0): float(x) for x in range(5)}
        r, ev = synthetic(dsda, grid, [(0, 0), (2, 0), (4, 0)], 3, predicate=hit)
        self.assertEqual(len(ev), 3)
        self.assertEqual(r["stop_reason"], "max_points_explored")
        self.assertEqual(r["target_stop_checks"], [])

    def test_scope_and_method_guards(self):
        for field, value in [
            ("scope", "process"),
            ("method", "rbfopt"),
            ("method", "uniform"),
        ]:
            job = deepcopy(self.jobs[0])
            job["spec"][field] = value
            with self.assertRaisesRegex(ValueError, "Only Grid D-SDA"):
                validate_job(job)

    def test_incomplete_and_duplicate_pairings_are_rejected(self):
        validate_cohort(self.jobs)
        for altered in (
            self.jobs[:-1],
            self.jobs + [self.jobs[0]],
            self.jobs[:-1] + [self.jobs[0]],
        ):
            with self.assertRaisesRegex(ValueError, "Incomplete or duplicate"):
                validate_cohort(altered)
        changed = deepcopy(self.jobs)
        changed[0]["spec"]["seed"] = 1
        with self.assertRaises(ValueError):
            validate_cohort(changed)

    def test_missing_lookup_and_duplicate_response_are_rejected(self):
        job = self.jobs[0]
        s = job["spec"]
        data = (HERE / "inputs/grids" / f"{s['case']}.csv").read_text().splitlines()
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "missing.csv"
            for bad in (data[:-1], data + [data[1]]):
                p.write_text("\n".join(bad) + "\n")
                with self.assertRaisesRegex(ValueError, "Missing or duplicate lookup"):
                    verify_grid(p, s)

    def test_solver_model_import_guard_is_retained(self):
        from runtime import BLOCKED, SolverBlocker

        guard = SolverBlocker()
        for name in (
            "pyomo",
            "gams",
            "pyscipopt",
            "rbfopt",
            "fmqa_benchmark",
            "case_studies",
        ):
            with self.assertRaisesRegex(RuntimeError, "prohibited"):
                guard.find_spec(name)
        BLOCKED.clear()

    def completed_fixture(self, directory):
        job = next(
            j
            for j in self.jobs
            if j["spec"]["case"] == "ackley"
            and j["spec"]["budget"] == 10
            and j["spec"]["seed"] == 0
        )
        source = HERE / "baseline_runs" / job["spec"]["job_id"]
        result = read(source / "result.json")
        self.assertTrue(result["algorithm_result"]["runs"][-1]["stopped_early"])
        result.update(
            target_stop_rule="adopted_analysis.hit",
            termination_callback=result["evaluations"],
            solver_calls=0,
        )
        result["algorithm_result"]["target_stop_checks"] = []
        directory.mkdir()
        write(directory / "result.json", result)
        (directory / "callbacks.jsonl").write_bytes(
            (source / "callbacks.jsonl").read_bytes()
        )
        (directory / "search.log").write_text(
            "Synthetic completion fixture from the archived Ackley B10 record.\n"
        )
        write(
            directory / "process.json",
            dict(returncode=0, watchdog_seconds=None, cpu=None),
        )
        return job

    def test_resume_validates_completed_record_without_search(self):
        import run

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "completed"
            job = self.completed_fixture(directory)
            run.mark_complete(HERE, job, directory)
            with patch.object(
                run, "execute_child", side_effect=AssertionError("Duplicate execution")
            ):
                record = run.validate_completed(HERE, job, directory)
            self.assertEqual(record["status"], "verified")
            (directory / "callbacks.jsonl").write_text("{}\n")
            with self.assertRaisesRegex(ValueError, "Completed run file changed"):
                run.validate_completed(HERE, job, directory)

    def test_unexpected_callback_path_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "changed"
            job = self.completed_fixture(directory)
            data = [
                json.loads(line)
                for line in (directory / "callbacks.jsonl").read_text().splitlines()
            ]
            data[4]["point"] = [30, 29]
            (directory / "callbacks.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in data)
            )
            with self.assertRaisesRegex(
                ValueError, "Unexpected callback path/value change"
            ):
                audit_one(HERE, job, directory)


if __name__ == "__main__":
    unittest.main(verbosity=2)
