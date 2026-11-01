"""Synthetic records only: no optimizer, NLP, SSH, or server experiment is run."""

import csv
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import control as C  # noqa: E402
import verify as V  # noqa: E402


def csv_file(path, records):
    fields = list(dict.fromkeys(k for r in records for k in r))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


@pytest.fixture(scope="module")
def a_output(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic_a")
    checks, summary, specs = [], [], []
    for budget, hits in ((10, 13), (30, 78), (50, 91), (70, 101), (100, 101)):
        for i in range(210):
            specs.append(
                dict(
                    job_id=f"g{i // 10}_B{budget}_seed{i % 10}",
                    scope="grid",
                    case=f"g{i // 10}",
                    budget=budget,
                    seed=i % 10,
                    lower=[0],
                    upper=[3],
                    starts=[[0], [1], [2]],
                    hit=i < hits,
                    index=i,
                )
            )
    for i in range(140):
        specs.append(
            dict(
                job_id=f"p{i // 10}_seed{i % 10}",
                scope="process",
                case=f"p{i // 10}",
                budget=25,
                seed=i % 10,
                lower=[0],
                upper=[3],
                starts=[[0], [1], [2]],
                hit=i < 79,
                index=i,
            )
        )
    jobs = []
    for source in specs:
        spec = {k: v for k, v in source.items() if k not in ("hit", "index")}
        jobs.append({"spec": spec})
        for variant in (
            ["grid"]
            if spec["scope"] == "grid"
            else ["single", "ranked", "ranked_random"]
        ):
            events = [
                dict(
                    index=i + 1,
                    point=[i],
                    accepted=True,
                    raw_objective=float(i if source["hit"] else i + 1),
                )
                for i in range(3)
            ]
            if variant in ("ranked", "ranked_random") and source["index"] == 79:
                events.append(
                    dict(index=4, point=[3], accepted=True, raw_objective=0.0)
                )
            best = min(e["raw_objective"] for e in events)
            directory = root / "runs" / (spec["job_id"] + "__" + variant)
            directory.mkdir(parents=True)
            V.write(
                directory / "result.json",
                dict(
                    spec=spec,
                    variant=variant,
                    reevaluate_explored=False,
                    status="completed",
                    error=None,
                    process_nlp_calls=0,
                    evaluations=len(events),
                    best_objective=best,
                    target=0.0,
                    hit=best == 0,
                ),
            )
            (directory / "callbacks.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in events)
            )
            checks.append(
                dict(
                    job_id=spec["job_id"],
                    variant=variant,
                    passed=True,
                    ok=True,
                    no_repeats=True,
                    legacy_reproduces_published=True,
                    published_distinct_prefix=True,
                    not_worse=True,
                    hit_kept=True,
                    first_descent_matches_single=True,
                    published_hit=False,
                )
            )
            summary.append({**spec, "variant": variant})
    V.write(root / "manifest.json", dict(git_head=C.PIN["A"], process_nlp_calls=0))
    V.write(root / "checks.json", dict(passed=True, jobs=1470, failures=[]))
    csv_file(root / "checks.csv", checks)
    csv_file(root / "runs.csv", summary)
    return root, jobs


def test_a_fixed_job_set_and_cross_check(a_output):
    root, jobs = a_output
    audit = V.audit_a(root, C.PIN["A"], jobs)
    assert audit["results"] == 1470 and audit["hits"]["single"] == 79
    assert audit["hits"]["ranked"] == audit["hits"]["ranked_random"] == 80


def test_a_repeated_coordinate_is_rejected(a_output):
    root, jobs = a_output
    path = root / "runs/g0_B10_seed0__grid/callbacks.jsonl"
    original = path.read_text()
    event = json.loads(original.splitlines()[0])
    path.write_text(original + json.dumps(event) + "\n")
    try:
        with pytest.raises(RuntimeError, match="repeats/budget"):
            V.audit_a(root, C.PIN["A"], jobs)
    finally:
        path.write_text(original)


def test_a_changed_plan_is_rejected(a_output):
    root, jobs = a_output
    with pytest.raises(RuntimeError, match="sealed input plan"):
        V.audit_a(root, C.PIN["A"], jobs[:-1])


def test_a_reported_failure_is_not_relabelled(a_output):
    root, jobs = a_output
    path = root / "checks.json"
    original = path.read_bytes()
    V.write(path, dict(passed=False, jobs=1470, failures=["synthetic failed prefix"]))
    try:
        with pytest.raises(RuntimeError, match="checks.json failed"):
            V.audit_a(root, C.PIN["A"], jobs)
    finally:
        path.write_bytes(original)


@pytest.fixture
def b_output(tmp_path):
    jobs = []
    starts = [[i, 0, 0, 0, 0, 0] for i in range(7)]
    for method in ("dsda", "rbfopt", "bam", "fmqa_sa", "uniform", "nomad", "miso"):
        for budget in (25, 50, 100):
            for seed in range(10):
                job = dict(
                    job_id=f"{method}_B{budget}_seed{seed}",
                    method=method,
                    budget=budget,
                    seed=seed,
                    starts=starts,
                    lower=[0] * 6,
                    upper=[6] * 6,
                    settings={},
                )
                jobs.append(job)
                directory = tmp_path / "runs" / job["job_id"]
                directory.mkdir(parents=True)
                ev = [
                    dict(
                        index=i + 1,
                        point=p,
                        accepted=True,
                        raw_objective=float(i),
                        point_cost_s=1,
                    )
                    for i, p in enumerate(starts)
                ]
                (directory / "callbacks.jsonl").write_text(
                    "".join(json.dumps(e) + "\n" for e in ev)
                )
                V.write(
                    directory / "result.json",
                    dict(
                        spec=job,
                        evaluations=7,
                        status="completed",
                        best_objective=0.0,
                        cpu=[4],
                        solved_now=0,
                        details={},
                    ),
                )
    V.write(tmp_path / "plan.json", dict(jobs=jobs))
    db = sqlite3.connect(tmp_path / "cache.sqlite")
    db.execute("create table meta (key text primary key,value text)")
    db.execute("create table responses (gaps text primary key,record text)")
    db.execute(
        "insert into meta values (?,?)",
        ("provenance", json.dumps({"solver": "conopt"})),
    )
    for i, p in enumerate(starts):
        db.execute(
            "insert into responses values (?,?)",
            (
                json.dumps(p),
                json.dumps(
                    dict(
                        accepted=True,
                        objective=float(i),
                        solve_wall_s=1,
                        solver_row=dict(solvestat=1, modelstat=2),
                    )
                ),
            ),
        )
    db.commit()
    db.close()
    return tmp_path


def test_b_keeps_all_210_in_denominator(b_output):
    directory = b_output / "runs" / "miso_B100_seed9"
    (directory / "result.json").unlink()
    V.write(directory / "worker_failure.json", dict(returncode=-9, timed_out=True))
    audit = V.audit_b(b_output)
    assert audit["planned"] == 210 and audit["completed"] == 209
    assert audit["worker_failures"] == audit["worker_timeouts"] == 1
    assert not audit["nlp_call_count_exact"]


def test_b_missing_terminal_record_blocks_collection(b_output):
    (b_output / "runs" / "miso_B100_seed9" / "result.json").unlink()
    with pytest.raises(RuntimeError, match="lack terminal records"):
        V.audit_b(b_output)


def test_b_changed_initial_order_is_rejected(b_output):
    path = b_output / "runs" / "nomad_B100_seed9" / "callbacks.jsonl"
    events = V.events(path)
    events[0], events[1] = events[1], events[0]
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    with pytest.raises(RuntimeError, match="initial order"):
        V.audit_b(b_output)


def test_mac_cannot_launch_experiments(monkeypatch):
    monkeypatch.setattr(C.platform, "system", lambda: "Darwin")
    with pytest.raises(RuntimeError, match="only on Dantzig"):
        C.host_guard()


def test_smt_siblings_are_never_two_workers(monkeypatch):
    monkeypatch.setattr(
        C.os, "sched_getaffinity", lambda pid: {0, 1, 8, 9}, raising=False
    )
    monkeypatch.setattr(C, "free_cores", lambda: ([], {0: 1, 1: 1, 8: 1, 9: 1}))
    monkeypatch.setattr(
        C,
        "topology",
        lambda cpu: dict(
            cpu=cpu, socket=0, core=cpu % 8, siblings=[cpu % 8, cpu % 8 + 8]
        ),
    )
    with pytest.raises(RuntimeError, match="SMT siblings"):
        C.choose_cpus(2, "0,8")
    assert [r["cpu"] for r in C.choose_cpus(2, "0,1")] == [0, 1]


def test_busy_cpu_zero_blocks_original_preflight(monkeypatch):
    monkeypatch.setattr(C.os, "sched_getaffinity", lambda pid: {0, 8}, raising=False)
    monkeypatch.setattr(C, "free_cores", lambda: ([], {0: 0.3, 8: 1}))
    monkeypatch.setattr(
        C, "topology", lambda cpu: dict(cpu=cpu, socket=0, core=0, siblings=[0, 8])
    )
    with pytest.raises(RuntimeError, match="currently busy"):
        C.choose_cpus(1, "0")


def test_head_mismatch_never_creates_worktree(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(C, "STATE", tmp_path)
    monkeypatch.setattr(C, "COORD", tmp_path / "coordination")
    monkeypatch.setattr(C, "inventory", lambda: None)
    (tmp_path / "source.git").mkdir()
    V.write(tmp_path / "SOURCE_MANIFEST.json", {"revision": C.PIN["A"]})
    commands = []

    def fake_git(*args, **kwargs):
        commands.append(args)
        if args == ("remote",):
            return ""
        if args == ("rev-parse", "refs/heads/pinned"):
            return "f" * 40
        return ""

    monkeypatch.setattr(C, "git", fake_git)
    with pytest.raises(RuntimeError, match="offline source HEAD differs"):
        C.prepare("A")
    assert not any(args[0] == "worktree" for args in commands)
    assert ("rev-parse", "FETCH_HEAD") not in commands
    assert not any(args[0] in ("fetch", "pull", "clone", "push") for args in commands)


def test_offline_preparation_uses_only_bundled_source(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROOT", tmp_path / "package")
    monkeypatch.setattr(C, "STATE", tmp_path / "package/state")
    monkeypatch.setattr(C, "REPO", tmp_path / "existing")
    monkeypatch.setattr(C, "COORD", tmp_path / "coordination")
    monkeypatch.setattr(C, "inventory", lambda: None)
    (C.ROOT / "source.git").mkdir(parents=True)
    V.write(C.ROOT / "SOURCE_MANIFEST.json", {"revision": C.PIN["A"]})
    commands = []

    def fake_git(*args, **kwargs):
        commands.append((args, kwargs.get("cwd")))
        if args[0] == "rev-parse":
            return C.PIN["A"]
        return ""

    monkeypatch.setattr(C, "git", fake_git)
    assert C.prepare("A") == tmp_path / "dsda_no_revisit"
    assert all(
        args[0] not in ("fetch", "pull", "clone", "push") for args, cwd in commands
    )
    assert all(
        cwd == C.ROOT / "source.git"
        for args, cwd in commands
        if args[0] in ("worktree", "fsck")
    )


def test_offline_source_with_network_remote_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(C, "STATE", tmp_path / "state")
    monkeypatch.setattr(C, "COORD", tmp_path / "coordination")
    monkeypatch.setattr(C, "inventory", lambda: None)
    (tmp_path / "source.git").mkdir()
    monkeypatch.setattr(C, "git", lambda *args, **kwargs: "origin")
    with pytest.raises(RuntimeError, match="network remote"):
        C.prepare("B")


def test_packages_do_not_share_physical_cores(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "COORD", tmp_path / "coordination")
    monkeypatch.setattr(C, "ROOT", tmp_path / "package_a")
    monkeypatch.setattr(C, "identity", lambda pid: str(pid))
    cores = [dict(cpu=c, socket=0, core=c, siblings=[c, c + 8]) for c in range(4)]
    monkeypatch.setattr(C, "free_cores", lambda: (cores, {c: 1 for c in range(12)}))
    a = C.acquire_cpus("A", 1)
    monkeypatch.setattr(C, "ROOT", tmp_path / "package_b")
    b = C.acquire_cpus("B", 16)
    assert len(a) == 1 and len(b) == 3
    assert not ({r["core"] for r in a} & {r["core"] for r in b})
    C.release_cpus("B")
    assert len(C.allocations()) == 1


def test_live_child_keeps_cpu_after_supervisor_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "COORD", tmp_path / "coordination")
    monkeypatch.setattr(C, "ROOT", tmp_path / "package")
    parent = C.os.getpid()
    child = parent + 1234
    living = {parent, child}
    monkeypatch.setattr(C, "identity", lambda pid: str(pid) if pid in living else None)
    cores = [dict(cpu=1, socket=0, core=1, siblings=[1, 9])]
    monkeypatch.setattr(C, "free_cores", lambda: (cores, {1: 1, 9: 1}))
    C.acquire_cpus("A", 1)
    C.hold_process("A", child)
    living.remove(parent)
    C.release_cpus("A")
    assert C.allocations()
    living.remove(child)
    C.release_cpus("A")
    assert not C.allocations()


def test_explicit_cpu_cannot_take_another_packages_smt_sibling(monkeypatch):
    monkeypatch.setattr(C.os, "sched_getaffinity", lambda pid: {1, 9}, raising=False)
    monkeypatch.setattr(C, "free_cores", lambda: ([], {1: 1, 9: 1}))
    monkeypatch.setattr(
        C, "topology", lambda cpu: dict(cpu=cpu, socket=0, core=1, siblings=[1, 9])
    )
    with pytest.raises(RuntimeError, match="another experiment"):
        C.choose_cpus(1, "9", reserved={(0, 1)})


def test_zip_paths_and_duplicate_members_are_rejected(tmp_path):
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as out:
        out.writestr("../outside", "x")
    with pytest.raises(RuntimeError, match="Unsafe"):
        V.zip_check(path)


def test_pack_return_keeps_original_bytes_and_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(C, "STATE", tmp_path / "state")
    destination = tmp_path / "results" / "synthetic"
    destination.mkdir(parents=True)
    (destination / "raw.txt").write_bytes(b"unchanged\r\n")
    C.pack_return("A", destination)
    with zipfile.ZipFile(tmp_path / "RETURN_A.zip") as out:
        assert out.read("synthetic/raw.txt") == b"unchanged\r\n"
    with pytest.raises(RuntimeError, match="Return already exists"):
        C.pack_return("A", destination)


def test_private_key_marker_blocks_publication(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("-----BEGIN PRIVATE KEY-----\nsynthetic-test-marker\n")
    with pytest.raises(RuntimeError, match="Credential/license content"):
        C.no_secret_files([path])


def test_readmes_have_no_hangul_and_no_optimizer_imports():
    assert not __import__("re").search(
        "[\uac00-\ud7af]", (ROOT / "README.md").read_text()
    )
    assert "import soogo" not in (ROOT / "control.py").read_text()
    assert "import PyNomad" not in (ROOT / "control.py").read_text()
