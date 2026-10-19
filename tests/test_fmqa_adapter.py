"""Small deterministic adapter tests; no archived campaign or process NLP solve."""
# ruff: noqa: E402 -- optional FMQA dependencies are checked before imports.
import hashlib
import itertools
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

pytest.importorskip("torch")
pytest.importorskip("dimod")
pytest.importorskip("dwave.samplers")

import dimod
import torch
from fmqa_benchmark.adapter import run_fmqa_sa
from fmqa_benchmark import qhd_surrogate
from fmqa_benchmark.optimizer import BinaryCoordinates, optimize, training_targets

CONFIG = dict(epochs=5, learning_rate=.01, num_reads=5, num_sweeps=20, time_limit=30)


@pytest.mark.parametrize("lower,upper", [([1, 1], [5, 5]), ([2, 2, 1], [3, 3, 3]), ([7, 1], [15, 9]), ([1, 0], [31, 3])])
def test_coordinate_round_trip_and_order(lower, upper):
    encoding = BinaryCoordinates(lower, upper)
    for point in encoding.lattice():
        bits = encoding.encode(point)
        assert encoding.decode(bits) == point
        assert bits == "".join(f"{v:0{hi.bit_length()}b}" for v, hi in zip(point, upper))
    with pytest.raises(ValueError):
        encoding.encode([hi + 1 for hi in upper])


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
    events, proposals = run()
    # Retain the public-adapter trajectory at the original 8897a8b head.
    assert events == [[1, 3], [2, 2], [3, 1], [3, 2], [1, 1], [3, 3], [2, 3], [1, 2]]
    assert (events, proposals) == run()


def test_vendor_files_are_exact_github_blobs():
    meta = qhd_surrogate.verify_sources()
    for name, digest in meta["github_blob_sha"].items():
        raw = (qhd_surrogate.VENDOR / name).read_bytes()
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == digest


def test_adapter_matches_direct_native_training_and_bqm_energies():
    import numpy as np
    import torch
    module, _ = qhd_surrogate.upstream()
    bits, target = ["00", "01", "11"], [1., .5, 0.]
    with qhd_surrogate.cpu_settings(), torch.random.fork_rng(devices=[]):
        torch.manual_seed(37)
        direct = module.FMBQM.from_data(np.array([[int(b) for b in x] for x in bits]),
                                      np.array(target), num_epoch=50, learning_rate=.01)
    wrapped = qhd_surrogate.train(bits, target, seed=37, epochs=50, learning_rate=.01)
    repeated = qhd_surrogate.train(bits, target, seed=37, epochs=50, learning_rate=.01)
    assert dict(direct.linear) == dict(wrapped.linear) == dict(repeated.linear)
    assert dict(direct.quadratic) == dict(wrapped.quadratic) == dict(repeated.quadratic)
    assert direct.offset == wrapped.offset == repeated.offset
    assert all(p.dtype == torch.float32 and p.device.type == "cpu" for p in wrapped.fm.parameters())
    bias, linear, quadratic = wrapped.fm.get_bhQ()
    np.fill_diagonal(quadratic, linear)
    scale = np.max(np.abs(quadratic))
    for x in itertools.product((0, 1), repeat=2):
        predicted = wrapped.fm(torch.tensor([x], dtype=torch.float32)).item()
        assert wrapped.energy(dict(enumerate(x))) == pytest.approx(predicted / scale, abs=1e-5)
    interop_threads = torch.get_num_interop_threads()
    with qhd_surrogate.cpu_settings() as settings:
        assert settings["threads"] == 1
        assert settings["interop_threads"] == interop_threads


@pytest.mark.parametrize("bits,targets", [
    (["0"], [0.]),
    (["0", "1"], [1., 1.]),
    (["000", "111", "101"], [0., 1., .5]),
    (["0" * 17, "1" * 17, "01" * 8 + "0"], [1., .5, 0.]),
])
def test_native_training_boundary_shapes_preserve_finite_repeatable_energies(bits, targets):
    # Cover scalar-sized batches, constant targets and wider FM interaction matrices.
    model = qhd_surrogate.train(bits, targets, seed=19, epochs=10, learning_rate=.01)
    repeated = qhd_surrogate.train(bits, targets, seed=19, epochs=10, learning_rate=.01)
    assert dict(model.linear) == dict(repeated.linear)
    assert dict(model.quadratic) == dict(repeated.quadratic)
    assert model.offset == repeated.offset
    width = len(bits[0])
    probes = np.array([[0] * width, [1] * width, *np.eye(width, dtype=int).tolist()])
    with torch.no_grad():
        predictions = model.fm(torch.tensor(probes, dtype=torch.float32, device="cpu")).numpy()
    assert predictions.shape == (len(probes),)
    assert np.isfinite(predictions).all()
    _, linear, quadratic = model.fm.get_bhQ()
    np.fill_diagonal(quadratic, linear)
    scale = np.max(np.abs(quadratic))
    assert np.isfinite(scale) and scale > 0
    energies = [model.energy(dict(enumerate(point))) for point in probes]
    np.testing.assert_allclose(energies, predictions / scale, rtol=1e-5, atol=1e-5)


def test_public_adapter_preserves_core_path_and_reports_effective_settings():
    from fmqa_benchmark.adapter import run_fmqa_sa

    def run(public):
        events, proposals = [], []
        kwargs = dict(on_evaluation=lambda e, s: events.append(e),
                      on_proposal=proposals.append)
        args = (lambda p: sum(p), [1, 1], [3, 3], [(1, 3), (2, 2), (3, 1)], 5, 7)
        if public:
            result = run_fmqa_sa(*args, config=CONFIG, **kwargs)
        else:
            result = optimize(*args, CONFIG, **kwargs)
        return result, events, proposals

    direct, events, proposals = run(False)
    wrapped, wrapped_events, wrapped_proposals = run(True)
    assert [e["point"] for e in events] == [e["point"] for e in wrapped_events]
    assert [e["raw_value"] for e in events] == [e["raw_value"] for e in wrapped_events]
    assert proposals == wrapped_proposals
    assert wrapped["best_value"] == direct["best_value"]
    assert wrapped["total_evals"] == direct["total_evals"] == 5
    assert wrapped["adapter"]["settings"] == CONFIG
    assert wrapped["adapter"]["upstream_commit"] == qhd_surrogate.COMMIT
    with pytest.raises(ValueError, match="Unknown FMQA adapter settings"):
        run_fmqa_sa(lambda p: pytest.fail("No callback expected"), [1], [3], [(1,)],
                    1, 0, config={"target_value": 0})


def test_source_tampering_is_rejected(tmp_path, monkeypatch):
    import shutil

    vendor = tmp_path / "qhd"
    shutil.copytree(qhd_surrogate.VENDOR, vendor)
    monkeypatch.setattr(qhd_surrogate, "VENDOR", vendor)
    source = vendor / "fmqa/fmqa/factorization_machine.py"
    source.write_bytes(source.read_bytes() + b"\n# modified\n")
    with pytest.raises(ValueError, match="source changed"):
        qhd_surrogate.verify_sources()


def _torch_settings():
    return (torch.get_default_dtype(), torch.get_default_device(),
            torch.get_num_threads(), torch.get_num_interop_threads(),
            torch.are_deterministic_algorithms_enabled(),
            torch.is_deterministic_algorithms_warn_only_enabled())


@pytest.mark.parametrize("failure", (None, "training", "objective"))
def test_public_adapter_preserves_caller_torch_settings(monkeypatch, failure):
    original = _torch_settings()
    original_rng = torch.random.get_rng_state()
    try:
        torch.set_default_dtype(torch.float64)
        torch.set_default_device("meta")
        torch.set_num_threads(2)
        torch.use_deterministic_algorithms(False, warn_only=True)
        expected = _torch_settings()
        calls = []
        weights = torch.ones(2, dtype=torch.float64, device="cpu")

        def objective(point):
            calls.append(tuple(point))
            assert _torch_settings() == expected
            value = float(torch.tensor(point, dtype=torch.get_default_dtype(), device="cpu") @ weights)
            if failure == "objective" and len(calls) == 4:
                raise RuntimeError("objective failed after fitting")
            return value

        if failure == "training":
            module, original_train = qhd_surrogate.upstream()

            def fail_after_training(*args, **kwargs):
                assert torch.get_default_dtype() == torch.float32
                assert torch.get_default_device() == torch.device("cpu")
                assert torch.get_num_threads() == 1
                assert torch.are_deterministic_algorithms_enabled()
                original_train(*args, **kwargs)
                raise RuntimeError("training failed after fitting")

            monkeypatch.setattr(qhd_surrogate, "upstream", lambda: (module, fail_after_training))

        args = (objective, [1, 1], [3, 3], [(1, 3), (2, 2), (3, 1)], 4, 7)
        if failure:
            with pytest.raises(RuntimeError, match=f"{failure} failed after fitting"):
                run_fmqa_sa(*args, config=CONFIG)
        else:
            result = run_fmqa_sa(*args, config=CONFIG)
            assert result["total_evals"] == 4
        assert len(calls) == (3 if failure == "training" else 4)
        assert _torch_settings() == expected
        assert torch.equal(torch.random.get_rng_state(), original_rng)
    finally:
        dtype, device, threads, _, deterministic, warn_only = original
        torch.set_default_dtype(dtype)
        torch.set_default_device(device)
        torch.set_num_threads(threads)
        torch.use_deterministic_algorithms(deterministic, warn_only=warn_only)
        torch.random.set_rng_state(original_rng)


def test_public_adapter_accepts_preconfigured_interop_runtime():
    # Interop can only be configured once, so exercise this in a fresh process.
    script = """
import torch
from fmqa_benchmark.adapter import run_fmqa_sa
torch.set_num_interop_threads(2)
calls = []
result = run_fmqa_sa(lambda p: calls.append(p) or sum(p), [1, 1], [3, 3],
                     [(1, 3), (2, 2), (3, 1)], 4, 7,
                     config={'epochs': 2, 'num_reads': 2, 'num_sweeps': 5})
assert result['total_evals'] == len(calls) == 4
assert torch.get_num_interop_threads() == 2
"""
    completed = subprocess.run([sys.executable, "-c", script],
                               cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("time_limit,expected_calls", ((0, 0), (30, 1)))
def test_public_adapter_large_box_small_budget(time_limit, expected_calls):
    calls = []
    result = run_fmqa_sa(lambda p: calls.append(p) or sum(p),
                         [0, 0], [10000, 10000], [(0, 0)], 1, 7,
                         config={"time_limit": time_limit})
    assert len(calls) == result["total_evals"] == expected_calls
    assert result["status"] == ("time_limit" if time_limit == 0 else "completed")


def test_public_adapter_counts_preparation_toward_deadline(monkeypatch):
    from fmqa_benchmark import optimizer

    clock = [0.0]
    original_prepare = BinaryCoordinates.__post_init__

    def prepare(encoding):
        original_prepare(encoding)
        clock[0] += 2.0

    monkeypatch.setattr(BinaryCoordinates, "__post_init__", prepare)
    monkeypatch.setattr(optimizer, "perf_counter", lambda: clock[0])
    calls = []
    result = run_fmqa_sa(lambda p: calls.append(p) or sum(p), [1], [3], [(1,)],
                         1, 0, config={"time_limit": 1})
    assert result["status"] == "time_limit"
    assert result["wall_time_s"] == 2.0
    assert calls == []


@pytest.mark.parametrize("upper,budget", (([3, 4], 12), ([10000, 10000], 4), ([2**32, 2**32], 4)))
def test_public_fallback_preserves_seeded_unseen_order(monkeypatch, upper, budget):
    from dwave.samplers import SimulatedAnnealingSampler
    from fmqa_benchmark import optimizer

    def trainer(bits, targets, **kwargs):
        return dimod.BinaryQuadraticModel({i: 0 for i in range(len(bits[0]))}, {}, 0, dimod.BINARY)

    def invalid_sample(self, model, **kwargs):
        return dimod.SampleSet.from_samples({i: 0 for i in model.variables}, dimod.BINARY, energy=0)

    def optimize_with_trainer(*args, **kwargs):
        return optimize(*args, trainer=trainer, **kwargs)

    monkeypatch.setattr("fmqa_benchmark.adapter.optimize", optimize_with_trainer)
    monkeypatch.setattr(SimulatedAnnealingSampler, "sample", invalid_sample)
    calls, proposals = [], []
    result = run_fmqa_sa(lambda p: calls.append(tuple(p)) or sum(p) % 1000, [1, 1], upper,
                         [(1, 1)], budget, 4, config=CONFIG, on_proposal=proposals.append)
    assert len(calls) == len(set(calls)) == budget
    assert result["fallback_count"] == budget - 1
    assert all(proposal["source"] == "uniform_unseen_fallback" for proposal in proposals)
    if upper == [3, 4]:
        # Independent legacy oracle: lexicographic product, then filter and index.
        rng = np.random.default_rng(np.random.SeedSequence(4).spawn(3)[2])
        expected = [(1, 1)]
        for _ in range(budget - 1):
            remaining = [p for p in itertools.product(range(1, 4), range(1, 5)) if p not in expected]
            expected.append(remaining[int(rng.integers(len(remaining)))])
        assert calls == expected
    assert optimizer.BinaryCoordinates([1, 1], upper).valid(calls[-1])
