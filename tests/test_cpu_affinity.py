"""CPU allocation rejects unsupported IDs and hyperthread siblings."""

from types import SimpleNamespace

import pytest

import cpu_affinity as affinity


@pytest.fixture
def linux(monkeypatch, tmp_path):
    state = {"cpus": {0, 1, 2, 3}}

    def set_affinity(pid, cpus):
        state["cpus"] = set(cpus)

    monkeypatch.setattr(affinity, "os", SimpleNamespace(
        sched_getaffinity=lambda pid: state["cpus"].copy(), sched_setaffinity=set_affinity))
    monkeypatch.setattr(affinity, "TOPOLOGY_ROOT", tmp_path)
    for cpu, core in ((0, 0), (1, 1), (2, 0), (3, 1)):
        directory = tmp_path / f"cpu{cpu}" / "topology"
        directory.mkdir(parents=True)
        for name, value in {"physical_package_id": "0", "core_id": str(core),
                            "thread_siblings_list": "0,2" if core == 0 else "1,3"}.items():
            (directory / name).write_text(value)
    return state


def test_explicit_cpu_and_record(linux):
    assert affinity.pin_cpu(2) == 2
    record = affinity.affinity_record(2)
    assert record["effective_cpus"] == [2]
    assert record["core_id"] == "0" and record["thread_siblings_list"] == "0,2"


def test_default_uses_first_allowed_cpu(linux):
    linux["cpus"] = {2, 3}
    assert affinity.pin_cpu() == 2


@pytest.mark.parametrize("cpu", [-1, 4])
def test_unavailable_cpu_never_silently_falls_back(linux, cpu):
    with pytest.raises(ValueError, match="not allowed"):
        affinity.pin_cpu(cpu)
    assert linux["cpus"] == {0, 1, 2, 3}


def test_pair_check_rejects_smt_siblings_without_changing_affinity(linux):
    with pytest.raises(ValueError, match="share a physical core"):
        affinity.check_cpu_pair(0, 2)
    assert affinity.check_cpu_pair(0, 1)["distinct_physical_cores"]
    assert linux["cpus"] == {0, 1, 2, 3}


@pytest.mark.parametrize("pair", [(0, 0), (0, 4)])
def test_pair_check_rejects_duplicate_or_unavailable_cpu(linux, pair):
    with pytest.raises(ValueError, match="distinct allowed"):
        affinity.check_cpu_pair(*pair)


def test_missing_topology_does_not_claim_separate_cores(linux, tmp_path):
    (tmp_path / "cpu2/topology/core_id").unlink()
    with pytest.raises(ValueError, match="cannot verify"):
        affinity.check_cpu_pair(0, 2)


def test_same_core_number_on_different_sockets_is_separate(linux, tmp_path):
    (tmp_path / "cpu2/topology/physical_package_id").write_text("1")
    assert affinity.check_cpu_pair(0, 2)["distinct_physical_cores"]


def test_explicit_cpu_unsupported_platform_fails(monkeypatch):
    monkeypatch.setattr(affinity, "os", SimpleNamespace())
    assert affinity.pin_cpu() is None
    with pytest.raises(ValueError, match="requires Linux"):
        affinity.pin_cpu(0)


def test_ineffective_affinity_change_fails(linux, monkeypatch):
    monkeypatch.setattr(affinity.os, "sched_setaffinity", lambda pid, cpus: None)
    with pytest.raises(RuntimeError, match="Failed to restrict"):
        affinity.pin_cpu(2)
