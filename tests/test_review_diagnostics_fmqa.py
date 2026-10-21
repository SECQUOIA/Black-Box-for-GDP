"""Manual FM weights and saved-prefix selection; no fitting or SA calls."""

import pytest
import shutil

from review_diagnostics.common import ROOT, read
from review_diagnostics.prepare import select


def test_selection_deduplicates_and_does_not_replace_absent_fallback():
    p = [
        {"iteration": 1, "source": "simulated_annealing"},
        {"iteration": 2, "source": "simulated_annealing"},
    ]
    selected, missing = select(p)
    assert selected == {1: ["first_simulated_annealing"], 2: ["last_proposal"]}
    assert missing == ["uniform_unseen_fallback"]
    p = [{"iteration": 1, "source": "uniform_unseen_fallback"}]
    selected, missing = select(p)
    assert selected == {1: ["first_uniform_unseen_fallback", "last_proposal"]}
    assert missing == ["simulated_annealing"]


@pytest.fixture
def historical(tmp_path):
    pytest.importorskip("torch")
    pytest.importorskip("dimod")
    from review_diagnostics.fmqa import load_historical

    selection = read(ROOT / "results/review_diagnostics_20261020/selection.json")
    return load_historical(selection["fmqa_cases"][0], tmp_path)


def test_nonzero_bias_interaction_scaling_and_zero_scale_guard(historical):
    from review_diagnostics.fmqa import synthetic

    qhd, _ = historical
    report = synthetic(qhd)
    for r in report["zero_scale_cases"]:
        assert r["Q_all_zero_before_scaling"] and r["scaling_factor"] == 0
        assert "invalid coefficients" in r["historical_wrapper_guard_exception"]
        assert not r["uniform_fallback_invoked"]
        assert r["training_calls"] == r["sa_calls"] == 0
    rows = {r["bits"]: r for r in report["nonzero_control"]["rows"]}
    assert [rows[b]["unscaled_qubo_with_bias"] for b in ("00", "01", "10", "11")] == [
        3,
        2,
        5,
        6,
    ]
    assert all(r["identity_pass"] and r["scaling_factor"] == 2 for r in rows.values())
    assert report["adam_default_weight_decay"] == 0


def test_domain_seen_rules_do_not_use_objective_or_feasibility(historical):
    from review_diagnostics.fmqa import classify

    _, optimizer = historical
    encoding = optimizer.BinaryCoordinates([1, 2], [9, 9])
    assert classify(encoding, "00000000", {(2, 4)})[1:] == (False, False, False)
    assert classify(encoding, encoding.encode([2, 4]), {(2, 4)})[1:] == (
        True,
        True,
        False,
    )
    # Structurally rejected Process points are still eligible FMQA candidates.
    assert classify(encoding, encoding.encode([8, 3]), {(2, 4)})[1:] == (
        True,
        False,
        True,
    )


def test_energy_enumeration_refuses_more_than_ten_bits(historical):
    from review_diagnostics.fmqa import exhaustive

    _, optimizer = historical
    with pytest.raises(ValueError, match="ten-bit"):
        exhaustive(None, optimizer.BinaryCoordinates([0, 0], [63, 63]), set())


def test_fit_exception_propagates_without_sampling_or_fallback(historical):
    _, optimizer = historical
    proposals = []

    def failed_trainer(*args, **kwargs):
        raise ValueError("PyTorch FMBQM has invalid coefficients, dtype or device")

    class NoSampler:
        def sample(self, *args, **kwargs):
            raise AssertionError("Sampling must not follow a fit exception")

    with pytest.raises(ValueError, match="invalid coefficients"):
        optimizer.optimize(
            lambda point: 0.0,
            [0, 0],
            [1, 1],
            [(0, 0), (0, 1), (1, 0)],
            4,
            0,
            {
                "epochs": 1,
                "learning_rate": 0.01,
                "time_limit": 30,
                "num_reads": 1,
                "num_sweeps": 1,
            },
            trainer=failed_trainer,
            sampler=NoSampler(),
            on_proposal=proposals.append,
        )
    assert not proposals


def test_selected_prefixes_have_no_future_observations():
    from review_diagnostics.prepare import records

    root = ROOT / "results/review_diagnostics_20261020"
    selection = read(root / "selection.json")
    assert sum(len(c["iterations"]) for c in selection["fmqa_cases"]) == 7
    for case in selection["fmqa_cases"]:
        events = records(
            (root / "inputs" / case["case"] / case["events_name"]).read_bytes()
        )
        if case["case"] == "rosenbrock":
            events = [r for r in events if r.get("event") == "evaluation"]
        for item in case["iterations"]:
            prefix = read(
                root
                / "fmqa"
                / f"{case['case']}_iteration{item['iteration']}"
                / "training_prefix.json"
            )
            assert (
                len(prefix["points"])
                == item["training_points"]
                == item["iteration"] + 2
            )
            assert prefix["points"] == [
                r["point"] for r in events[: item["training_points"]]
            ]
            assert prefix["fm_seed"] == item["fm_seed"]


def test_missing_or_changed_local_inputs_rejected_before_fitting(tmp_path):
    from review_diagnostics.verify import verify_inputs

    source = ROOT / "results/review_diagnostics_20261020"
    for name in ("selection.json", "manifest.json"):
        shutil.copyfile(source / name, tmp_path / name)
    shutil.copytree(source / "inputs", tmp_path / "inputs")
    path = tmp_path / "inputs/rosenbrock/proposals.jsonl"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Local input copy changed"):
        verify_inputs(tmp_path)
    path.unlink()
    with pytest.raises(ValueError, match="Local input copy changed"):
        verify_inputs(tmp_path)
