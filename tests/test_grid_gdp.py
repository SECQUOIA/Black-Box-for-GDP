"""Original-formula GDPs reproduce the archived discrete grid problems."""
# ruff: noqa: E402 -- optional GDP dependencies must be checked before imports.

import csv
import math
from pathlib import Path

import pytest

pyo = pytest.importorskip("pyomo.environ")
pytest.importorskip("networkx")

from pyomo.gdp import Disjunction

from gdp_models.grid import (
    BOUNDS,
    GRID_NAMES,
    audit_grid,
    build_all_grid_gdps,
    build_grid_gdp,
    fix_grid_point,
)


GRID_DIR = Path(__file__).resolve().parents[1] / "benchmark_grids"


def _csv_rows(name):
    with (GRID_DIR / f"{name}.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


def _values(name):
    return {(int(row["x"]), int(row["y"])): float(row["z_norm"])
            for row in _csv_rows(name)}


def _points(points):
    return {tuple(point) for point in points}


def _assert_constraints_satisfied(model, atol=1e-10):
    for constraint in model.component_data_objects(pyo.Constraint, active=True):
        body = pyo.value(constraint.body)
        assert math.isfinite(body), constraint.name
        if constraint.has_lb():
            assert body >= pyo.value(constraint.lower) - atol, constraint.name
        if constraint.has_ub():
            assert body <= pyo.value(constraint.upper) + atol, constraint.name


def test_all_archived_grid_problems_are_available():
    expected = {path.stem for path in GRID_DIR.glob("*.csv")}
    assert len(GRID_NAMES) == len(set(GRID_NAMES)) == 21
    assert set(GRID_NAMES) == expected == set(BOUNDS)
    models = build_all_grid_gdps()
    assert set(models) == expected
    assert len({id(model) for model in models.values()}) == 21


@pytest.mark.parametrize("name", GRID_NAMES)
def test_all_961_objective_values_and_minimizers_match_csv(name):
    report = audit_grid(name)
    values = _values(name)
    minimum = min(values.values())
    minima = {point for point, value in values.items() if abs(value - minimum) <= 1e-12}
    exact_minima = {point for point, value in values.items() if value == minimum}
    assert report["name"] == name
    assert report["points_checked"] == len(values) == 961
    assert math.isfinite(report["max_abs_error"])
    assert report["max_abs_error"] <= 1e-12
    assert _points(report["csv_minimizers"]) == minima
    assert _points(report["model_minimizers"]) == minima
    assert _points(report["exact_csv_minimizers"]) == exact_minima


@pytest.mark.parametrize("name", GRID_NAMES)
def test_model_uses_two_exactly_one_coordinate_disjunctions(name):
    model = build_grid_gdp(name, verify_csv=False)
    xmin, xmax, ymin, ymax = BOUNDS[name]
    assert list(model.I) == list(range(31))
    assert len(model.Xchoice) == len(model.Ychoice) == 31
    assert len(model.pick_x.disjuncts) == len(model.pick_y.disjuncts) == 31
    assert model.pick_x.xor and model.pick_y.xor
    assert len(list(model.component_data_objects(Disjunction, active=True))) == 2
    assert (pyo.value(model.gx[0]), pyo.value(model.gx[30])) == (xmin, xmax)
    assert (pyo.value(model.gy[0]), pyo.value(model.gy[30])) == (ymin, ymax)
    assert model.x.bounds == (xmin, xmax)
    assert model.y.bounds == (ymin, ymax)
    assert model.obj.sense == pyo.minimize
    assert pyo.value(model.normalization_range) > 0


@pytest.mark.parametrize("name", GRID_NAMES)
@pytest.mark.parametrize("transformation", ["gdp.bigm", "gdp.hull"])
def test_all_grids_support_standard_gdp_transformations(name, transformation):
    model = build_grid_gdp(name, verify_csv=False)
    pyo.TransformationFactory(transformation).apply_to(model)
    assert not list(model.component_data_objects(Disjunction, active=True))
    assert list(model.component_data_objects(pyo.Constraint, active=True))


@pytest.mark.parametrize("name", GRID_NAMES)
def test_fixing_a_grid_point_yields_feasible_csv_objective(name):
    values = _values(name)
    # Boundaries, nonsymmetric interior points, and every archived tied optimum
    # expose coordinate swaps, wrong domains, and approximate argmin handling.
    minimum = min(values.values())
    points = {(0, 0), (0, 30), (30, 0), (30, 30), (4, 7), (15, 15), (23, 11)}
    points.update(point for point, value in values.items() if abs(value - minimum) <= 1e-12)
    original = build_grid_gdp(name, verify_csv=False)
    for point in sorted(points):
        model = original.clone()
        assert fix_grid_point(model, point) is model
        assert model.x.fixed and model.y.fixed
        assert pyo.value(model.x) == pyo.value(model.gx[point[0]])
        assert pyo.value(model.y) == pyo.value(model.gy[point[1]])
        assert not list(model.component_data_objects(Disjunction, active=True))
        assert not [var for var in model.component_data_objects(pyo.Var, active=True)
                    if (var.is_integer() or var.is_binary()) and not var.fixed]
        _assert_constraints_satisfied(model)
        actual = pyo.value(model.obj)
        assert math.isfinite(actual)
        assert actual == pytest.approx(values[point], rel=0, abs=1e-12)
        raw = pyo.value(model.raw_objective)
        assert actual == pytest.approx(
            (raw - pyo.value(model.normalization_min)) / pyo.value(model.normalization_range),
            rel=0, abs=1e-14,
        )


@pytest.mark.parametrize("point", [(15, 15), (15, 7), (4, 15), (0, 30), (14, 16)])
def test_csendes_zero_extension_and_reciprocals_remain_defined(point):
    model = fix_grid_point(build_grid_gdp("csendes", verify_csv=False), point)
    for coordinate, reciprocal in ((model.x, model.rx), (model.y, model.ry)):
        value = pyo.value(coordinate)
        expected = 0.0 if value == 0 else 1.0 / value
        assert reciprocal.fixed
        assert pyo.value(reciprocal) == pytest.approx(expected, rel=0, abs=1e-12)
    _assert_constraints_satisfied(model)
    assert pyo.value(model.obj) == pytest.approx(_values("csendes")[point], rel=0, abs=1e-12)


@pytest.mark.parametrize("damage", [
    "altered_objective", "missing_row", "duplicate_coordinate", "fractional_coordinate",
    "out_of_bounds_coordinate", "nan_objective", "infinite_objective",
])
def test_audit_and_default_build_reject_changed_or_malformed_csv(tmp_path, damage):
    rows = _csv_rows("ackley")
    if damage == "altered_objective":
        rows[42]["z_norm"] = str(float(rows[42]["z_norm"]) + 0.01)
    elif damage == "missing_row":
        rows.pop()
    elif damage == "duplicate_coordinate":
        rows[-1] = dict(rows[0])
    elif damage == "fractional_coordinate":
        rows[0]["x"] = "0.5"
    elif damage == "out_of_bounds_coordinate":
        rows[0]["y"] = "31"
    elif damage == "nan_objective":
        rows[42]["z_norm"] = "nan"
    elif damage == "infinite_objective":
        rows[42]["z_norm"] = "inf"
    with (tmp_path / "ackley.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Point", "x", "y", "z_norm"])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError):
        audit_grid("ackley", csv_dir=tmp_path)
    with pytest.raises(ValueError):
        build_grid_gdp("ackley", csv_dir=tmp_path)


def test_missing_csv_is_reported_and_formula_model_can_be_built_without_it(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        audit_grid("ackley", csv_dir=tmp_path)
    model = build_grid_gdp("ackley", verify_csv=False, csv_dir=tmp_path)
    assert len(model.pick_x.disjuncts) == 31


@pytest.mark.parametrize("name", ["", "not_a_grid", "../ackley"])
def test_unknown_grid_names_are_rejected(name):
    with pytest.raises(ValueError):
        build_grid_gdp(name)
    with pytest.raises(ValueError):
        audit_grid(name)


@pytest.mark.parametrize("point", [
    (-1, 0), (31, 0), (0, 31), (1,), (1, 2, 3), (0.5, 1), (math.nan, 1), (math.inf, 1),
])
def test_invalid_grid_points_are_rejected(point):
    with pytest.raises(ValueError):
        fix_grid_point(build_grid_gdp("ackley", verify_csv=False), point)
