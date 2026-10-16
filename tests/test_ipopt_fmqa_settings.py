"""IPOPT runners consume the scoped FMQA settings API without process solves."""

import importlib
import json

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("dimod")
pytest.importorskip("dwave.samplers")


@pytest.mark.parametrize("module_name", ["ipopt_dfo_cstr", "ipopt_dfo_non_cstr"])
@pytest.mark.parametrize("optimizer_failure", [False, True])
def test_settings_are_serializable_and_restored_before_callbacks(
    module_name, optimizer_failure, monkeypatch, tmp_path
):
    runner = importlib.import_module(module_name)
    from fmqa_benchmark import optimizer

    def fake_optimize(objective, lower, upper, starts, budget, seed, settings, **kwargs):
        assert torch.get_default_dtype() == torch.float64
        objective(starts[0])
        if optimizer_failure:
            raise RuntimeError("optimizer probe failure")
        return {"status": "probe_complete"}

    monkeypatch.setattr(optimizer, "optimize", fake_optimize)
    spec = {"method": "fmqa_sa", "seed": 0, "settings": runner.SETTINGS["fmqa_sa"],
            "lower": [1, 1], "upper": [3, 3], "starts": [[1, 1], [2, 2], [3, 3]], "budget": 4}
    calls = []
    original_dtype = torch.get_default_dtype()
    try:
        torch.set_default_dtype(torch.float64)
        if optimizer_failure:
            with pytest.raises(RuntimeError, match="optimizer probe failure"):
                runner.optimize(spec, lambda point: calls.append(point) or 1.0, {}, tmp_path)
        else:
            result = runner.optimize(spec, lambda point: calls.append(point) or 1.0, {}, tmp_path)
            assert result == {"status": "probe_complete"}
        assert torch.get_default_dtype() == torch.float64
        assert calls == [[1, 1]]
        recorded = json.loads((tmp_path / "actual_settings.json").read_text())["torch"]
        assert recorded["dtype"] == "float32"
        assert recorded["device"] == "cpu" and recorded["threads"] == 1
        assert recorded["deterministic_algorithms"] is True
    finally:
        torch.set_default_dtype(original_dtype)
