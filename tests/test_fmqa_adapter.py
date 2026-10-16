"""Small deterministic adapter tests; no archived campaign or process NLP solve."""
# ruff: noqa: E402 -- optional FMQA dependencies are checked before imports.
import hashlib
import itertools

import numpy as np
import pytest

pytest.importorskip("torch")
pytest.importorskip("dimod")
pytest.importorskip("dwave.samplers")

import dimod
from fmqa_benchmark import qhd_surrogate
from fmqa_benchmark.optimizer import BinaryCoordinates, optimize, training_targets

CONFIG = dict(epochs=5, learning_rate=.01, num_reads=5, num_sweeps=20, time_limit=30)


def native():
    qhd_surrogate.cpu_settings()


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
    assert run() == run()


def test_vendor_files_are_exact_github_blobs():
    meta = qhd_surrogate.verify_sources()
    for name, digest in meta["github_blob_sha"].items():
        raw = (qhd_surrogate.VENDOR / name).read_bytes()
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == digest


def test_adapter_matches_direct_native_training_and_bqm_energies():
    native()
    import numpy as np
    import torch
    module, _ = qhd_surrogate.upstream()
    bits, target = ["00", "01", "11"], [1., .5, 0.]
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
    assert qhd_surrogate.cpu_settings()["threads"] == qhd_surrogate.cpu_settings()["interop_threads"] == 1


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
