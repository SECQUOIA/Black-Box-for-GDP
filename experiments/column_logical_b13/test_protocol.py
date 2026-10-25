"""No optimizer runs: validate frozen inputs, callback handling and CPU guards."""

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

import analyze
import common
import cpu_guard
import runner
import worker

PACKAGE = Path(os.environ.get("COLUMN_PACKAGE", Path(__file__).resolve().parent))


@pytest.fixture
def inputs():
    return common.verify_package(PACKAGE)


def load_core(group):
    path = PACKAGE / "frozen" / group / "ipopt_dfo_non_cstr.py"
    spec = importlib.util.spec_from_file_location("frozen_column_" + group, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_domain_plan_and_original_attempts(inputs):
    plan, costs = inputs
    assert len(plan) == 50 and len(costs) == 64
    assert sum(r["accepted"] == "True" for r in costs.values()) == 29
    assert all(r["cost_source"] == "original" for r in costs.values())
    assert (
        common.read(PACKAGE / "provenance/original_3430_input_audit.json")[
            "planned_jobs"
        ]
        == 3430
    )
    assert (
        common.read(PACKAGE / "provenance/logic_verification.json")["full_external_box"]
        == 225
    )
    assert (
        common.read(PACKAGE / "input_verification.json")["old_lhc_designs_reproduced"]
        == 10
    )
    for seed in range(10):
        starts = [j["spec"]["starts"] for j in plan if j["spec"]["seed"] == seed]
        assert all(p == starts[0] for p in starts)
        assert len(set(map(tuple, starts[0]))) == 3


@pytest.mark.parametrize(
    "change", ["duplicate", "budget", "bounds", "initial", "genetic", "cpu", "watchdog"]
)
def test_plan_corruption_rejected(inputs, change):
    plan = deepcopy(inputs[0])
    if change == "duplicate":
        plan[-1] = deepcopy(plan[0])
    elif change == "budget":
        plan[0]["spec"]["budget"] = 16
    elif change == "bounds":
        plan[0]["spec"]["upper"] = [15, 9]
    elif change == "initial":
        plan[0]["spec"]["starts"].reverse()
    elif change == "genetic":
        next(j for j in plan if j["spec"]["method"] == "rbfopt")["spec"]["settings"][
            "global_search_method"
        ] = "solver"
    elif change == "cpu":
        plan[0]["cpu"] = 3
    else:
        plan[0]["hard_seconds"] = 1800
    with pytest.raises(ValueError):
        common.validate_plan(plan)


@pytest.mark.parametrize("method", common.METHODS)
def test_rejection_policy_budget_and_terminal_target(inputs, tmp_path, method):
    plan, costs = inputs
    job = deepcopy(next(j for j in plan if j["spec"]["method"] == method))
    core = load_core(job["frozen"])
    rejected = [list(p) for p, r in costs.items() if r["accepted"] == "False"][:3]
    job["spec"]["starts"] = (
        rejected  # Synthetic oracle protocol fixture, not a real seed run.
    )
    oracle = worker.audited_oracle(core, job["spec"], costs, tmp_path)
    for point in rejected:
        oracle(point)
    kind = "nan" if method == "bam" else "+inf" if method == "fmqa_sa" else "finite"
    assert all(e["method_value_kind"] == kind for e in oracle.events)
    if kind == "finite":
        assert all(e["method_value"] == 1e6 for e in oracle.events)
    for _ in range(9):
        oracle(rejected[0])
    if method == "bam":
        assert oracle([13, 4]) == job["target"]
    else:
        with pytest.raises(core.BudgetStop):
            oracle([13, 4])
    assert len(oracle.events) == 13 and oracle.events[-1]["accepted"]
    metric, _ = common.measure(
        job["spec"],
        oracle.events,
        {"status": "budget_completed", "recorded_search_wall_s": 1},
        costs,
        job["target"],
    )
    assert metric["target_hit"] and metric["first_hit"] == 13
    assert metric["completion_s"] == pytest.approx(
        1
        - sum(e["lookup_wall_s"] for e in oracle.events)
        + sum(float(costs[tuple(e["point"])]["total_wall_s"]) for e in oracle.events)
    )
    with pytest.raises(Exception):
        oracle(rejected[0])
    assert oracle.audit_budget_overrun and oracle.call_count == 13
    assert (
        common.events(tmp_path / "callback_overrun_audit.jsonl")[0]["csv_read"] is False
    )


@pytest.mark.parametrize("method", common.METHODS)
@pytest.mark.parametrize("swallowed", [False, True])
def test_worker_never_labels_extra_request_as_budget_completion(
    inputs, tmp_path, monkeypatch, method, swallowed
):
    job = deepcopy(next(j for j in inputs[0] if j["spec"]["method"] == method))
    core = load_core(job["frozen"])

    def fake_optimize(spec, oracle, config, directory):
        for point in spec["starts"] + [spec["starts"][0]] * 10:
            try:
                oracle(point)
            except core.BudgetStop:
                pass
        try:
            oracle(spec["starts"][0])
        except RuntimeError:
            if not swallowed:
                raise
        return {"success": True}

    # Uniform has its own frozen sampling loop; exercise it via the same mocked
    # optimizer entry point while preserving this oracle's uniform responses.
    if method == "uniform_without_replacement":
        job["spec"]["method"] = "dsda"
    monkeypatch.setattr(core, "optimize", fake_optimize)
    monkeypatch.setattr(worker.os, "sched_getaffinity", lambda pid: {2}, raising=False)
    monkeypatch.setattr(worker, "ROOT", PACKAGE)
    worker.execute(job, tmp_path, inputs[1], core)
    result = common.read(tmp_path / "result.json")
    assert result["status"] == "execution_failed" and result["callback_count"] == 13
    assert result["callback_budget_overrun"]


def test_failed_target_run_is_not_a_success(inputs, tmp_path):
    job = deepcopy(inputs[0][0])
    costs = inputs[1]
    job["spec"]["starts"] = [[13, 4], [13, 3], [12, 3]]
    core = load_core(job["frozen"])
    oracle = core.Oracle(job["spec"], costs, tmp_path)
    for p in job["spec"]["starts"]:
        oracle(p)
    metric, _ = common.measure(
        job["spec"],
        oracle.events,
        {"status": "execution_failed", "recorded_search_wall_s": 1},
        costs,
        job["target"],
    )
    assert metric["category"] == "execution_failed" and not metric["target_hit"]


def test_import_blocker_prohibits_process_model_and_legacy_lookup():
    blocker = load_core("original").ProcessModelImportBlocker()
    for name in (
        "gdp_models.models",
        "gdp.column",
        "case_studies.column_case",
        "cstr_box_ipopt",
    ):
        with pytest.raises(ImportError):
            blocker.find_spec(name, None)
    assert blocker.find_spec("pyomo.environ", None) is None


def test_uniform_keeps_same_rng_stream_and_has_no_replacement(inputs, monkeypatch):
    monkeypatch.syspath_prepend(str(PACKAGE / "frozen/sampling"))
    from review_comparison.worker import sampling_points

    for job in inputs[0]:
        if job["spec"]["method"] == "uniform_without_replacement":
            points, settings = sampling_points(job["sampling_job"])
            assert points[:3] == job["spec"]["starts"] and len(points) == 13
            assert (
                len(set(map(tuple, points))) == 13
                and set(map(tuple, points)) <= common.POINTS
            )
            assert (
                settings["seed_material"]
                == f"review-sampling-v1:process:column:{job['spec']['seed']}:uniform_without_replacement"
            )


def test_settings_rejects_unrelated_option_change(inputs, tmp_path):
    job = next(j for j in inputs[0] if j["spec"]["method"] == "rbfopt")
    common.write(tmp_path / "actual_settings.json", job["expected_settings"])
    worker.check_settings(job, tmp_path)
    changed = deepcopy(job["expected_settings"])
    changed["num_cpus"] = 2
    common.write(tmp_path / "actual_settings.json", changed)
    with pytest.raises(ValueError):
        worker.check_settings(job, tmp_path)


def test_idle_cpu_requires_all_intervals_and_siblings():
    samples = [{2: (i * 100, i * 100), 50: (i * 100, i * 100)} for i in range(7)]
    assert cpu_guard.decide([2, 50], samples, [{}] * 7, [], [])[0] == []
    samples[3][50] = (300, 290)
    assert cpu_guard.decide([2, 50], samples, [{}] * 7, [], [])[0]


@pytest.mark.parametrize(
    "reason", ["pinned_sleeping", "active_broad", "unknown", "scheduler"]
)
def test_cpu_guard_rejects_occupied_or_uncertain_core(reason):
    samples = [{2: (i * 100, i * 100), 50: (i * 100, i * 100)} for i in range(7)]
    process = dict(
        pid=9,
        tid=9,
        command="python existing_job.py",
        allowed=[50],
        ticks=0,
        start_ticks=99,
        last_cpu=50,
    )
    groups = [{} for _ in samples]
    unknown = []
    scheduler = []
    if reason == "pinned_sleeping":
        groups[0] = {"9": process}
    elif reason == "active_broad":
        process["allowed"] = list(range(96))
        process["last_cpu"] = 6
        groups[0] = {"9": process}
        groups[1] = {"9": {**process, "ticks": 1}}
    elif reason == "unknown":
        unknown = [{"pid": 9}]
    else:
        scheduler = ["No inspectable allocation"]
    assert cpu_guard.decide([2, 50], samples, groups, unknown, scheduler)[0]


def test_lock_survives_inherited_worker_and_blocks_duplicate(tmp_path):
    import subprocess

    with runner.locked(tmp_path) as fd:
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(1)"], pass_fds=(fd,)
        )
    try:
        with pytest.raises(RuntimeError):
            with runner.locked(tmp_path):
                pytest.fail("Duplicate lock acquired")
    finally:
        child.wait()
    with runner.locked(tmp_path):
        pass


def test_sealed_failure_is_preserved_and_tampering_rejected(tmp_path):
    directory = tmp_path / "jobs/example/attempt_0001"
    directory.mkdir(parents=True)
    common.write(directory / "result.json", {"status": "execution_failed"})
    common.write(
        directory / "terminal.json",
        {"files_sha256": {"result.json": common.sha(directory / "result.json")}},
    )
    assert analyze.selected(tmp_path, "example") == directory
    common.write(directory / "result.json", {"status": "completed"})
    with pytest.raises(ValueError):
        analyze.selected(tmp_path, "example")


def test_pending_analysis_retains_fifty_slots_and_no_fake_results(tmp_path):
    output = tmp_path / "analysis"
    result = analyze.generate(tmp_path, output, root=PACKAGE, plots=False)
    assert (
        result["sealed_jobs"] == 0
        and result["pending_jobs"] == 50
        and result["actual_callbacks"] == 0
    )
    methods = common.read(output / "methods.json")
    for row in methods:
        if row["condition"] == "64_B13":
            assert (
                row["target_hits"] is None
                and row["median_reconstructed_completion_s"] is None
            )
            assert row["denominator"] == 10 and row["pending"] == 10
    assert len(common.read(output / "runs.json")) == 100
    assert (
        json.loads((output / "manifest.json").read_text())[
            "new_optimizer_calls_during_analysis"
        ]
        == 0
    )


def test_sealed_failure_keeps_denominator_and_interrupted_attempt_costs(
    inputs, tmp_path
):
    plan, costs = inputs
    job = plan[0]
    failed = tmp_path / "jobs" / job["spec"]["job_id"] / "attempt_0001"
    failed.mkdir(parents=True)
    common.write(failed / "job.json", job)
    common.write(
        failed / "result.json",
        {
            "status": "execution_failed",
            "process_nlp_calls": 0,
            "recorded_search_wall_s": 1.0,
            "error": "synthetic worker failure",
        },
    )
    core = load_core(job["frozen"])
    oracle = core.Oracle(job["spec"], costs, failed)
    for point in job["spec"]["starts"]:
        oracle(point)
    common.write(
        failed / "terminal.json",
        {
            "files_sha256": {
                p.name: common.sha(p) for p in failed.iterdir() if p.is_file()
            }
        },
    )
    interrupted_job = plan[1]
    interrupted = tmp_path / "jobs" / interrupted_job["spec"]["job_id"] / "attempt_0001"
    interrupted.mkdir(parents=True)
    load_core(interrupted_job["frozen"]).Oracle(
        interrupted_job["spec"], costs, interrupted
    )(interrupted_job["spec"]["starts"][0])
    report = analyze.generate(
        tmp_path, tmp_path / "analysis", root=PACKAGE, plots=False
    )
    assert report["sealed_jobs"] == report["failed_jobs"] == 1
    assert report["pending_jobs"] == 49
    assert report["actual_callbacks"] == 4 and report["sealed_run_callbacks"] == 3
    assert report["interrupted_attempt_callbacks"] == 1
    row = next(
        r
        for r in common.read(tmp_path / "analysis/methods.json")
        if r["condition"] == "64_B13" and r["method"] == job["spec"]["method"]
    )
    assert row["denominator"] == 10 and row["failed"] == 1 and row["target_hits"] == 0
    assert row["pending"] == 9
    assert all(
        r["evaluation_record_sha256"]
        for r in common.rows(tmp_path / "analysis/callback_ledger.csv")
    )


@pytest.mark.parametrize("last_cpu", [2, 50, 6])
def test_unrestricted_affinity_distinguished_from_observed_core_usage(last_cpu):
    samples = [{2: (i * 1000, i * 1000), 50: (i * 1000, i * 1000)} for i in range(7)]
    process = dict(
        pid=1,
        tid=1,
        command="python other.py",
        allowed=list(range(96)),
        ticks=0,
        start_ticks=5,
        last_cpu=last_cpu,
        state="S",
    )
    groups = [{"1": {**process, "ticks": i}} for i in range(7)]
    blocked, _ = cpu_guard.decide(
        [2, 50], samples, groups, [], [], online_cpus=set(range(96))
    )
    assert bool(blocked) == (last_cpu in (2, 50))


@pytest.mark.parametrize("constrained", [True, False])
def test_wide_explicit_compute_affinity_is_still_protected(constrained):
    samples = [{2: (i * 1000, i * 1000), 50: (i * 1000, i * 1000)} for i in range(7)]
    process = dict(
        pid=1,
        tid=1,
        command="python other.py",
        allowed=list(range(64 if constrained else 96)),
        ticks=0,
        start_ticks=5,
        last_cpu=6,
        state="S",
    )
    blocked, _ = cpu_guard.decide(
        [2, 50], samples, [{"1": process}] * 7, [], [], online_cpus=set(range(96))
    )
    assert bool(blocked) == constrained


def test_reported_low_load_does_not_alone_imply_occupation():
    busy = {
        2: [
            0.4608294930875576,
            1.3824884792626728,
            0.9216589861751152,
            0,
            0.9259259259259259,
            0.46296296296296297,
        ],
        50: [
            0,
            0,
            0.9259259259259259,
            1.8604651162790697,
            2.7522935779816513,
            0.46511627906976744,
        ],
    }
    samples = [{cpu: (0, 0) for cpu in busy}]
    for index in range(6):
        samples.append(
            {
                cpu: (
                    (index + 1) * 100000,
                    samples[-1][cpu][1] + 100000 - round(busy[cpu][index] * 1000),
                )
                for cpu in busy
            }
        )
    assert not cpu_guard.decide(
        [2, 50], samples, [{}] * 7, [], [], online_cpus=set(range(96))
    )[0]
    # The supplied load series alone does not certify that process activity is absent.
    p = dict(
        pid=1,
        tid=1,
        command="python pinned.py",
        allowed=[50],
        ticks=0,
        start_ticks=5,
        last_cpu=50,
        state="S",
    )
    assert cpu_guard.decide(
        [2, 50], samples, [{"1": p}] * 7, [], [], online_cpus=set(range(96))
    )[0]


@pytest.mark.parametrize("interval_busy", [[6, 0, 0, 0, 0, 0], [3, 3, 3, 3, 3, 3]])
def test_peak_or_sustained_background_load_blocks_launch(interval_busy):
    samples = [{2: (0, 0), 50: (0, 0)}]
    for index, busy in enumerate(interval_busy):
        samples.append(
            {
                2: ((index + 1) * 1000, samples[-1][2][1] + 1000 - busy * 10),
                50: ((index + 1) * 1000, (index + 1) * 1000),
            }
        )
    assert cpu_guard.decide(
        [2, 50], samples, [{}] * 7, [], [], online_cpus=set(range(96))
    )[0]


def test_running_new_thread_on_sibling_blocks_even_without_tick_delta():
    samples = [{2: (i * 1000, i * 1000), 50: (i * 1000, i * 1000)} for i in range(7)]
    p = dict(
        pid=1,
        tid=1,
        command="new-job",
        allowed=list(range(96)),
        ticks=0,
        start_ticks=5,
        last_cpu=50,
        state="R",
    )
    assert cpu_guard.decide(
        [2, 50],
        samples,
        [{}, {}, {}, {}, {}, {}, {"1": p}],
        [],
        [],
        online_cpus=set(range(96)),
    )[0]


def test_cpu_blocker_is_printed_in_launch_log(capsys, tmp_path):
    record = {
        "permitted_to_start": False,
        "siblings": [2, 50],
        "busy_percent_by_interval": [{2: 0, 50: 0}],
        "busy_percent_over_window": {2: 0, 50: 0},
        "blockers": ["Existing process 123 occupies CPU 50"],
    }
    runner.report_occupancy(record, tmp_path / "occupancy.json")
    output = capsys.readouterr().out
    assert (
        "CPU_CHECK=blocked" in output
        and "CPU_BLOCK=Existing process 123 occupies CPU 50" in output
    )
    assert "CPU_OCCUPANCY_RECORD=" in output


def background_fixture(
    state="S", cpu=2, command="/opt/microsoft/mdatp/sbin/wdavdaemon", allowed=None
):
    samples = []
    totals2 = [0, 217, 433, 649, 865, 1081, 1297]
    totals50 = [0, 217, 433, 649, 866, 1082, 1299]
    for i in range(7):
        samples.append(
            {
                2: (totals2[i], totals2[i] - (1 if i else 0)),
                50: (totals50[i], totals50[i] - (1 if i else 0) - (1 if i == 6 else 0)),
            }
        )
    process = dict(
        pid=1748688,
        tid=1748716,
        command=command,
        allowed=list(range(96)) if allowed is None else allowed,
        ticks=0,
        start_ticks=100,
        last_cpu=cpu,
        state=state,
    )
    groups = [{str(process["tid"]): {**process, "ticks": i}} for i in range(7)]
    return samples, groups


@pytest.mark.parametrize("state", ["R", "S"])
@pytest.mark.parametrize("cpu", [2, 50])
def test_low_load_wdav_activity_is_recorded_without_claiming_compute_occupation(
    state, cpu
):
    samples, groups = background_fixture(state=state, cpu=cpu)
    blockers, loads = cpu_guard.decide(
        [2, 50], samples, groups, [], [], online_cpus=set(range(96))
    )
    assert not blockers
    assert max(v for interval in loads for v in interval.values()) == pytest.approx(
        0.4608294930875576
    )
    assert 100 * (samples[-1][2][0] - samples[-1][2][1]) / samples[-1][2][
        0
    ] == pytest.approx(0.07710100231302919)
    assert 100 * (samples[-1][50][0] - samples[-1][50][1]) / samples[-1][50][
        0
    ] == pytest.approx(0.15396458814472824)


@pytest.mark.parametrize(
    "command",
    [
        "/tmp/wdavdaemon",
        "/opt/microsoft/mdatp/sbin/wdavdaemon-copy",
        "python /opt/microsoft/mdatp/sbin/wdavdaemon",
        "python experiment.py",
        "/usr/local/bin/unknown-simulation",
    ],
)
def test_unrelated_or_lookalike_tasks_remain_blockers(command):
    samples, groups = background_fixture(command=command)
    assert cpu_guard.decide(
        [2, 50], samples, groups, [], [], online_cpus=set(range(96))
    )[0]


@pytest.mark.parametrize(
    "kind",
    ["constrained", "missing_topology", "busy", "unknown_permissions", "scheduler"],
)
def test_background_classification_never_bypasses_other_availability_checks(kind):
    samples, groups = background_fixture(
        allowed=[2, 50] if kind == "constrained" else None
    )
    if kind == "busy":
        samples = [{2: (i * 1000, i * 900), 50: (i * 1000, i * 1000)} for i in range(7)]
    assert cpu_guard.decide(
        [2, 50],
        samples,
        groups,
        [{"pid": 1}] if kind == "unknown_permissions" else [],
        ["No allocation"] if kind == "scheduler" else [],
        online_cpus=None if kind == "missing_topology" else set(range(96)),
    )[0]


def test_background_activity_is_printed_and_retained(capsys, tmp_path):
    _, groups = background_fixture()
    record = {
        "permitted_to_start": True,
        "siblings": [2, 50],
        "busy_percent_by_interval": [{2: 0.1, 50: 0.2}],
        "busy_percent_over_window": {2: 0.1, 50: 0.2},
        "blockers": [],
        "background_services_assessed_by_load": list(groups[-1].values()),
    }
    runner.report_occupancy(record, tmp_path / "occupancy.json")
    assert "CPU_BACKGROUND pid=1748688" in capsys.readouterr().out
