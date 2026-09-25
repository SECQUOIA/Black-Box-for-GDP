"""Protocol, FM mathematics, sampling isolation and archived-run integrity."""

import csv
import itertools
import json
import math
import subprocess
import sys
import zipfile

import numpy as np
import pytest

pytest.importorskip("dimod")
pytest.importorskip("dwave.samplers")

import dimod

from fmqa_benchmark.optimizer import BinaryCoordinates, optimize, training_targets
from fmqa_benchmark.protocol import point_hash, reference_plan, verify_lookup_sources
from fmqa_benchmark.surrogate import fit_bqm, prediction_and_gradients, train
from fmqa_benchmark_runner import ROOT, preflight, save, validate_job
from fmqa_compare import audit_fmqa, combine, result_directory


CONFIG = dict(epochs=5, learning_rate=.01, num_reads=5, num_sweeps=20, time_limit=30)


def test_original_matrix_and_coordinates():
    plan = reference_plan()
    assert len(plan) == 139
    assert len({p["initial_design_sha256"] for p in plan}) == 89
    assert {s["grid_size"] for s in plan if s["case_name"] == "cstr"} == {5, 10, 15, 20, 25, 30}
    for p in plan:
        assert p["initial_design_sha256"] == point_hash(p["starting_points"])
        assert p["n_starts"] == len(p["starting_points"]) == 3
    cstr = reference_plan(["cstr"], [5], [0])[0]
    assert cstr["starting_points"] == [[1, 2], [5, 5], [3, 2]]
    assert cstr["max_evaluations"] == 8
    assert len(verify_lookup_sources()) == 9


@pytest.mark.parametrize("lower,upper", [([1, 1], [5, 5]), ([2, 2, 1], [3, 3, 3]), ([7, 1], [15, 9]), ([1, 0], [31, 3])])
def test_coordinate_round_trip_and_order(lower, upper):
    encoding = BinaryCoordinates(lower, upper)
    for point in encoding.lattice():
        bits = encoding.encode(point)
        assert encoding.decode(bits) == point
        assert bits == "".join(f"{v:0{hi.bit_length()}b}" for v, hi in zip(point, upper))
    with pytest.raises(ValueError):
        encoding.encode([hi + 1 for hi in upper])


def test_fm_gradient_and_quadratic_energy():
    rng = np.random.default_rng(1)
    x = np.array(list(itertools.product([0, 1], repeat=3)), dtype=float)
    y = rng.normal(size=len(x))
    params = [rng.normal(size=1), rng.normal(size=3), rng.normal(size=(8, 3))]
    predictions, gradients = prediction_and_gradients(x, y, *params)
    b, h, v = params
    bqm = dimod.BinaryQuadraticModel(dict(enumerate(h)),
                                    {(i, j): v[:, i] @ v[:, j] for i in range(3) for j in range(i + 1, 3)},
                                    b[0], dimod.BINARY)
    np.testing.assert_allclose(predictions, bqm.energies(x))
    epsilon = 1e-6
    for parameter, gradient in zip(params, gradients):
        for index in np.ndindex(parameter.shape):
            original = parameter[index]
            parameter[index] = original + epsilon
            plus = np.mean((prediction_and_gradients(x, y, *params)[0] - y)**2)
            parameter[index] = original - epsilon
            minus = np.mean((prediction_and_gradients(x, y, *params)[0] - y)**2)
            parameter[index] = original
            assert gradient[index] == pytest.approx((plus - minus) / (2 * epsilon), rel=1e-5, abs=1e-6)


def test_original_training_entry_and_seeded_fit():
    options = dict(seed=12, epochs=150, learning_rate=.01)
    first = train(["00", "01", "10", "11"], [0, .25, .5, 1], **options)
    second = train(["00", "01", "10", "11"], [0, .25, .5, 1], **options)
    direct = fit_bqm([[0, 0], [0, 1], [1, 0], [1, 1]], [0, .25, .5, 1],
                     seed=12, num_epoch=150, learning_rate=.01)
    assert first == second == direct
    assert max(abs(v) for v in [*first.linear.values(), *first.quadratic.values()]) == pytest.approx(1)
    with pytest.raises(ValueError):
        train(["00", "11"], [0, np.inf], **options)


def test_first_adam_step_matches_mxnet_update_convention():
    x = np.array([[0, 0], [0, 1], [1, 1]], dtype=float)
    y = np.array([0, .5, 1])
    rng = np.random.default_rng(41)
    parameters = [rng.normal(0, .01, 1), rng.normal(0, .01, 2), rng.normal(0, .01, (8, 2))]
    _, gradients = prediction_and_gradients(x, y, *parameters)
    for p, gradient in zip(parameters, gradients):
        g = gradient / len(x)
        mean, variance = .1 * g, .001 * g**2
        p -= (.01 * np.sqrt(.001) / .1) * mean / (np.sqrt(variance) + 1e-8)
    b, h, v = parameters
    quadratic = v[:, 0] @ v[:, 1]
    scale = max(abs(quadratic), max(abs(h)))
    actual = fit_bqm(x, y, seed=41, num_epoch=1, learning_rate=.01)
    assert actual.offset == pytest.approx(b[0] / scale)
    np.testing.assert_allclose(list(actual.linear.values()), h / scale)
    assert actual.quadratic[(0, 1)] == pytest.approx(quadratic / scale)


def test_observed_targets_only():
    np.testing.assert_array_equal(training_targets([np.inf, -2, 4, np.nan]), [2, 0, 1, 2])
    np.testing.assert_array_equal(training_targets([5, 5, np.inf]), [0, 0, 2])
    np.testing.assert_array_equal(training_targets([np.inf, np.inf]), [2, 2])


def test_no_extra_objective_calls_and_infeasible_counts():
    calls, events, proposals = [], [], []
    starts = [(1, 1), (3, 3), (2, 2)]

    def objective(point):
        calls.append(tuple(point))
        return float("inf") if point == (1, 1) else sum(point)

    def trainer(bits, targets, **kwargs):
        assert len(bits) == len(targets) == len(calls)
        np.testing.assert_array_equal(targets, training_targets([np.inf if p == (1, 1) else sum(p) for p in calls]))
        return dimod.BinaryQuadraticModel({i: 0 for i in range(4)}, {}, 0, dimod.BINARY)

    class InvalidSampler:
        def sample(self, *args, **kwargs):
            return dimod.SampleSet.from_samples({i: 0 for i in range(4)}, dimod.BINARY, energy=0)

    result = optimize(objective, [1, 1], [3, 3], starts, 9, 4, CONFIG,
                      trainer=trainer, sampler=InvalidSampler(),
                      on_evaluation=lambda e, s: events.append(e), on_proposal=proposals.append)
    assert calls[:3] == starts
    assert len(calls) == len(set(calls)) == result["total_evals"] == 9
    assert result["fallback_count"] == result["adaptive_evals"] == 6
    assert result["status"] == "completed"
    assert events[0]["lookup_feasible"] is False
    assert events[0]["raw_value"] is None
    assert len(proposals) == 6
    assert result["best_value"] == 3


def test_real_seeded_sa_repeats_trajectory():
    def run():
        events, proposals = [], []
        optimize(lambda p: sum(v**2 for v in p), [1, 1], [3, 3], [(1, 3), (2, 2), (3, 1)], 8, 42, CONFIG,
                 on_evaluation=lambda e, s: events.append(e["point"]), on_proposal=proposals.append)
        return events, proposals
    assert run() == run()


@pytest.fixture(scope="module")
def archived_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("fmqa-run")
    command = [sys.executable, str(ROOT / "fmqa_benchmark_runner.py"), "run", "--cases", "cstr",
               "--cstr-sizes", "5", "--seeds", "0", "--epochs", "5", "--num-reads", "5",
               "--num-sweeps", "20", "--output-root", str(root)]
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
    directory = next(p for p in root.iterdir() if p.is_dir())
    return directory, command


def test_archived_pairing_and_resume(archived_run, tmp_path):
    directory, command = archived_run
    assert len(audit_fmqa(directory)["plan"]) == 1
    result = next(directory.glob("jobs/*/result.json"))
    before = result.read_bytes()
    completed = subprocess.run(command + ["--resume", str(directory)], check=True,
                               capture_output=True, text=True, timeout=60)
    assert "SKIP" in completed.stdout
    assert result.read_bytes() == before
    with result_directory(directory.with_suffix(".zip")) as extracted:
        output = combine(extracted, tmp_path / "comparison")
    with output.open() as handle:
        records = list(csv.DictReader(handle))
    assert len(records) == 4
    assert {r["method"] for r in records} == {"FMQA-SA", "DSDA", "RBFOpt", "BAM 5.0.0"}
    assert len({(r["csv_name"], r["seed"], r["n_starts"], r["max_evals"]) for r in records}) == 1


def test_tampered_trace_and_partial_result_rejected(archived_run, tmp_path):
    import shutil
    directory, _ = archived_run
    copied = tmp_path / "copy"
    shutil.copytree(directory, copied)
    spec = json.loads((copied / "run.json").read_text())["plan"][0]
    job = copied / "jobs" / spec["job_id"]
    path = job / "evaluations.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    events[0]["raw_value"] = -999
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    with pytest.raises(ValueError, match="checksum"):
        audit_fmqa(copied)
    with pytest.raises(ValueError, match="objective table"):
        validate_job(job, spec)
    path.write_text("\n".join(json.dumps(e) for e in events[:2]) + "\n")
    with pytest.raises(ValueError, match="callback count"):
        validate_job(job, spec)


def test_trace_allows_only_tiny_platform_float_parsing_differences(archived_run, tmp_path):
    import shutil
    directory, _ = archived_run
    copied = tmp_path / "copy"
    shutil.copytree(directory, copied)
    spec = json.loads((copied / "run.json").read_text())["plan"][0]
    job = copied / "jobs" / spec["job_id"]
    path = job / "evaluations.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    # Use a non-incumbent feasible event, so the original trajectory stays exact.
    event = next(e for e in events if e["lookup_feasible"] and e["value"] > e["incumbent"])
    original = event["raw_value"]
    event["raw_value"] = event["value"] = math.nextafter(original, math.inf)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    validate_job(job, spec)
    event["raw_value"] = event["value"] = original + 1e-8
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    with pytest.raises(ValueError, match="objective table"):
        validate_job(job, spec)


def test_resume_rejects_changed_hyperparameters(archived_run):
    directory, command = archived_run
    result = subprocess.run(command + ["--resume", str(directory), "--epochs", "6"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert "Resume requires identical" in result.stderr


def test_timeout_preserves_completed_initial_evaluations(tmp_path):
    from fmqa_benchmark.optimizer import BudgetExpired
    from fmqa_benchmark.protocol import problem
    spec = reference_plan(["cstr"], [5], [0])[0]
    oracle = problem(spec)
    events = []

    def expired(*args, **kwargs):
        raise BudgetExpired()

    state = optimize(oracle["objective"], oracle["lower"], oracle["upper"], spec["starting_points"],
                     spec["max_evaluations"], 0, CONFIG, trainer=expired,
                     on_evaluation=lambda e, s: events.append(e))
    assert state["status"] == "time_limit"
    assert state["total_evals"] == 3
    save(tmp_path / "result.json", {"spec": spec, **state})
    (tmp_path / "evaluations.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    assert validate_job(tmp_path, spec)["adaptive_evals"] == 0


def test_unsafe_result_zip_rejected(tmp_path):
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../escape", "bad")
    with pytest.raises(ValueError, match="Unsafe"):
        with result_directory(path):
            pass


def test_standalone_bundle(tmp_path):
    from fmqa_benchmark_runner import bundle
    from fmqa_benchmark.protocol import sha
    output = tmp_path / "runner.zip"
    bundle(output)
    with zipfile.ZipFile(output) as archive:
        archive.extractall(tmp_path)
        names = archive.namelist()
    assert all(".venv" not in p and "bamlice" not in p for p in names)
    root = tmp_path / "fmqa_runner"
    for line in (root / "RUNNER_SHA256SUMS").read_text().splitlines():
        digest, relative = line.split("  ", 1)
        assert sha(root / relative) == digest
    result = subprocess.run([sys.executable, "fmqa_benchmark_runner.py", "check"], cwd=root,
                            check=True, capture_output=True, text=True, timeout=60)
    assert json.loads(result.stdout)["runs"] == 139


def test_preflight_local_cpu_backend():
    metadata = preflight()
    assert "local CPU" in metadata["sampler"]
    assert all(value == "1" for value in metadata["thread_environment"].values())


def test_grid_original_matrix_and_initial_coordinates():
    from fmqa_benchmark.grid_protocol import reference_grid_plan, verify_grid_sources
    from fmqa_benchmark.protocol import problem
    plan = reference_grid_plan()
    assert len(plan) == 1050
    assert len({s["csv_name"] for s in plan}) == 21
    assert len({(s["csv_name"], s["seed"]) for s in plan}) == 210
    assert {s["max_evaluations"] for s in plan} == {10, 30, 50, 70, 100}
    assert {s["case_name"] for s in plan} == {"grid"}
    assert len(verify_grid_sources()) == 21
    spec = reference_grid_plan(["ackley"], [0], [10])[0]
    assert spec["starting_points"] == [[4, 7], [30, 30], [12, 11]]
    oracle = problem(spec)
    assert oracle["lower"] == [0, 0] and oracle["upper"] == [30, 30]
    assert oracle["target"] == pytest.approx(0)
    for name in ["unknown", "../ackley"]:
        with pytest.raises(ValueError):
            reference_grid_plan([name])


def test_grid_only_entry_result_archive_pairing_and_resume(tmp_path):
    from fmqa_benchmark_runner import GRID_KIND
    command = [sys.executable, str(ROOT / "fmqa_grid_benchmark.py"), "run", "--grids", "ackley",
               "--grid-budgets", "10", "--seeds", "0", "--epochs", "5", "--num-reads", "5",
               "--num-sweeps", "20", "--output-root", str(tmp_path / "runs")]
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
    directory = next(p for p in (tmp_path / "runs").iterdir() if p.is_dir())
    run = audit_fmqa(directory)
    assert run["kind"] == GRID_KIND and run["dataset"] == "grid"
    assert not (directory / "process_case_studies.csv").exists()
    assert (directory / "benchmark.csv").exists()
    result = subprocess.run(command + ["--resume", str(directory)], check=True,
                            capture_output=True, text=True, timeout=60)
    assert "SKIP" in result.stdout
    with result_directory(directory.with_suffix(".zip")) as extracted:
        output = combine(extracted, tmp_path / "comparison")
    assert output.name == "benchmark.csv"
    with output.open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 4
    assert {r["csv_name"] for r in rows} == {"ackley.csv"}
    result = subprocess.run([sys.executable, str(ROOT / "fmqa_grid_benchmark.py"), "plan", "--dataset", "case"],
                            capture_output=True, text=True)
    assert result.returncode != 0


def test_grid_bundle_uses_separate_folder(tmp_path):
    from fmqa_benchmark_runner import bundle
    archive_path = tmp_path / "grid.zip"
    bundle(archive_path, dataset="grid")
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert all(n.startswith("fmqa_grid_runner/") for n in names)
        assert "fmqa_grid_runner/fmqa_grid_benchmark.py" in names
        assert "fmqa_grid_runner/cpu_affinity.py" in names
        assert sum(n.startswith("fmqa_grid_runner/benchmark_grids/") and n.endswith(".csv") for n in names) == 21


def test_grid_runtime_note_does_not_assign_old_overlap_to_rerun():
    from fmqa_compare import grid_runtime_note
    old = {"created_utc": "2026-09-22T19:38:07.711180+00:00", "cpu": 0,
           "runtime": {"host": "dantzig.ecn.purdue.edu"}}
    assert "overlapped" in grid_runtime_note(old)
    rerun = {**old, "created_utc": "2026-09-25T00:00:00+00:00"}
    assert "overlapped" not in grid_runtime_note(rerun)
    assert "pinned to CPU 0" in grid_runtime_note(rerun)
    assert "not verified" in grid_runtime_note(rerun)
