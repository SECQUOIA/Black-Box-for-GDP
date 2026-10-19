"""Analytic GDPs on the 21 recorded 31-by-31 benchmark lattices.

The objective is an algebraic expression, never a lookup of CSV objective
values. CSVs independently check the expression and its sampled minimizers.
Run ``python -m gdp_models.grid validate`` to audit all 20,181 grid points.
"""

import argparse
import csv
from functools import lru_cache
import hashlib
import io
import json
import math
from pathlib import Path

import pyomo.environ as pyo
from pyomo.gdp import Disjunct, Disjunction


GRID_DIR = Path(__file__).resolve().parents[1] / "benchmark_grids"
GRID_SIZE = 31
CSV_ATOL = 1e-12
TARGET_TOLERANCE = 1e-5
FORMULA_SOURCE_COMMIT = "11ba8728a107d6d16ed63e72d334a66662f9ebc1"
FORMULA_SOURCE_PATH = "qhdopt_gdp.py"

# Physical coordinates, rather than the integer indices stored in the CSVs.
BOUNDS = {
    "ackley": (-5., 5., -5., 5.),
    "alpine1": (0., 10., 0., 10.),
    "alpine2": (0., 1000., 0., 1000.),
    "bohachevsky2": (-100., 100., -100., 100.),
    "camel3": (-5., 5., -5., 5.),
    "csendes": (-1., 1., -1., 1.),
    "deflected_corrugated_spring": (0., 10., 0., 10.),
    "dropwave": (-5.12, 5.12, -5.12, 5.12),
    "easom": (-10., 10., -10., 10.),
    "griewank": (-600., 600., -600., 600.),
    "holder_table": (-10., 10., -10., 10.),
    "hosaki": (0., 5., 0., 6.),
    "levy": (-10., 10., -10., 10.),
    "levy13": (-10., 10., -10., 10.),
    "michalewicz": (0., math.pi, 0., math.pi),
    "rastrigin": (-5.12, 5.12, -5.12, 5.12),
    "rosenbrock": (-2., 2., -1., 3.),
    "shubert": (0., 10., 0., 10.),
    "styblinski_tang": (-5., 5., -5., 5.),
    "sum_of_squares": (-10., 10., -10., 10.),
    "xin_she_yang3": (-20., 20., -20., 20.),
}
GRID_NAMES = tuple(BOUNDS)
FORMULA_NOTES = {
    "csendes": "Squared oscillatory factor; zero extension, no epsilon shift.",
    "shubert": "Historical three-term by two-term modified Shubert function.",
    "xin_she_yang3": (
        "Historical CSV variant: positive second term and unscaled y**6; "
        "not the canonical Xin-She Yang 3. Exponential underflow creates float-zero ties."
    ),
}


def _name(name):
    if not isinstance(name, str):
        raise ValueError("Grid name must be a string")
    name = name.lower().removesuffix(".csv")
    if name not in BOUNDS:
        raise ValueError(f"Unknown grid {name!r}; choose from {GRID_NAMES}")
    return name


def _coordinates(name):
    xmin, xmax, ymin, ymax = BOUNDS[name]
    # Preserve the historical order of floating-point operations.
    return (
        tuple(xmin + (i / (GRID_SIZE - 1)) * (xmax - xmin) for i in range(GRID_SIZE)),
        tuple(ymin + (i / (GRID_SIZE - 1)) * (ymax - ymin) for i in range(GRID_SIZE)),
    )


def _raw_expression(name, x, y, ops=math, reciprocals=None):
    """Same analytic expression for numeric auditing and symbolic Pyomo use."""
    sin, cos, exp, sqrt = ops.sin, ops.cos, ops.exp, ops.sqrt
    pi = math.pi
    if name == "ackley":
        return (-20 * exp(-.2 * sqrt(.5 * (x**2 + y**2)))
                - exp(.5 * (cos(2 * pi * x) + cos(2 * pi * y))) + 20 + exp(1))
    if name == "alpine1":
        return abs(x * sin(x) + .1 * x) + abs(y * sin(y) + .1 * y)
    if name == "alpine2":
        return -sqrt(x * y) * sin(x) * sin(y)
    if name == "bohachevsky2":
        return x**2 + 2 * y**2 - .3 * cos(3 * pi * x) * cos(4 * pi * y) + .3
    if name == "camel3":
        return 2 * x**2 - 1.05 * x**4 + x**6 / 6 + x * y + y**2
    if name == "csendes":
        if reciprocals is None:
            reciprocals = (0. if x == 0 else 1 / x, 0. if y == 0 else 1 / y)
        rx, ry = reciprocals
        return x**6 * (2 + sin(rx))**2 + y**6 * (2 + sin(ry))**2
    if name == "deflected_corrugated_spring":
        r2 = (x - 5)**2 + (y - 5)**2
        return .1 * r2 - cos(5 * sqrt(r2))
    if name == "dropwave":
        return -(1 + cos(12 * sqrt(x**2 + y**2))) / (.5 * (x**2 + y**2) + 2)
    if name == "easom":
        return -cos(x) * cos(y) * exp(-((x - pi)**2 + (y - pi)**2))
    if name == "griewank":
        return (x**2 + y**2) / 4000 - cos(x) * cos(y / sqrt(2)) + 1
    if name == "holder_table":
        return -abs(sin(x) * cos(y) * exp(abs(1 - sqrt(x**2 + y**2) / pi)))
    if name == "hosaki":
        return (1 - 8 * x + 7 * x**2 - 7 / 3 * x**3 + 1 / 4 * x**4) * y**2 * exp(-y)
    if name == "levy":
        return (sin(pi * (1 + (x - 1) / 4))**2
                + ((x - 1) / 4)**2 * (1 + 10 * sin(pi * (1 + (x - 1) / 4) + 1)**2)
                + ((y - 1) / 4)**2 * (1 + sin(2 * pi * (1 + (y - 1) / 4))**2))
    if name == "levy13":
        return (sin(3 * pi * x)**2 + (x - 1)**2 * (1 + sin(3 * pi * y)**2)
                + (y - 1)**2 * (1 + sin(2 * pi * y)**2))
    if name == "michalewicz":
        return -sin(x) * sin(x**2 / pi)**20 - sin(y) * sin(2 * y**2 / pi)**20
    if name == "rastrigin":
        return x**2 - 10 * cos(2 * pi * x) + y**2 - 10 * cos(2 * pi * y) + 20
    if name == "rosenbrock":
        return (1 - x)**2 + 100 * (y - x**2)**2
    if name == "shubert":
        return ((cos(2 * x + 1) + 2 * cos(3 * x + 2) + 3 * cos(4 * x + 3))
                * (cos(2 * y + 1) + cos(y + 2)))
    if name == "styblinski_tang":
        return (1 / 78) * .5 * (x**4 - 16 * x**2 + 5 * x + y**4 - 16 * y**2 + 5 * y)
    if name == "sum_of_squares":
        return x**2 + 2 * y**2
    if name == "xin_she_yang3":
        return exp(-((x / 15)**6 + y**6)) + 2 * exp(-(x**2 + y**2)) * cos(x)**2 * cos(y)**2
    raise ValueError(f"Unknown grid {name!r}")


@lru_cache(maxsize=len(GRID_NAMES))
def _normalization(name):
    xs, ys = _coordinates(name)
    values = [_raw_expression(name, x, y) for x in xs for y in ys]
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"Non-finite analytic sample for {name}")
    low, high = min(values), max(values)
    if high <= low:
        raise ValueError(f"Degenerate analytic normalization for {name}")
    return low, high - low


def _assign_point(model, point):
    i, j = point
    x, y = pyo.value(model.gx[i]), pyo.value(model.gy[j])
    model.x.set_value(x)
    model.y.set_value(y)
    if model.grid_name == "csendes":
        model.rx.set_value(0. if x == 0 else 1 / x)
        model.ry.set_value(0. if y == 0 else 1 / y)


def build_grid_gdp(name, *, verify_csv=True, csv_dir=GRID_DIR):
    """Build a fresh analytic GDP; independently verify all CSV values by default.

    Turning verification off never changes the objective, its coefficients, or
    its domain. It only omits access to the reference CSV.
    """
    name = _name(name)
    xmin, xmax, ymin, ymax = BOUNDS[name]
    xs, ys = _coordinates(name)
    low, span = _normalization(name)
    m = pyo.ConcreteModel(name=f"grid_{name}")
    m.grid_name = name
    m.I = pyo.RangeSet(0, GRID_SIZE - 1)
    m.gx = pyo.Param(m.I, initialize=dict(enumerate(xs)))
    m.gy = pyo.Param(m.I, initialize=dict(enumerate(ys)))
    m.x = pyo.Var(bounds=(xmin, xmax), initialize=xs[15])
    m.y = pyo.Var(bounds=(ymin, ymax), initialize=ys[15])
    if name == "csendes":
        xr = tuple(0. if x == 0 else 1 / x for x in xs)
        yr = tuple(0. if y == 0 else 1 / y for y in ys)
        m.rx = pyo.Var(bounds=(min(xr), max(xr)), initialize=xr[15])
        m.ry = pyo.Var(bounds=(min(yr), max(yr)), initialize=yr[15])

    def x_choice(disjunct, i):
        disjunct.fix_x = pyo.Constraint(expr=m.x == m.gx[i])
        if name == "csendes":
            disjunct.fix_reciprocal = pyo.Constraint(expr=m.rx == xr[i])

    def y_choice(disjunct, j):
        disjunct.fix_y = pyo.Constraint(expr=m.y == m.gy[j])
        if name == "csendes":
            disjunct.fix_reciprocal = pyo.Constraint(expr=m.ry == yr[j])

    m.Xchoice = Disjunct(m.I, rule=x_choice)
    m.Ychoice = Disjunct(m.I, rule=y_choice)
    m.pick_x = Disjunction(expr=[m.Xchoice[i] for i in m.I], xor=True)
    m.pick_y = Disjunction(expr=[m.Ychoice[j] for j in m.I], xor=True)
    m.ix = pyo.Expression(expr=sum(i * m.Xchoice[i].binary_indicator_var for i in m.I))
    m.iy = pyo.Expression(expr=sum(j * m.Ychoice[j].binary_indicator_var for j in m.I))
    reciprocals = (m.rx, m.ry) if name == "csendes" else None
    m.raw_objective = pyo.Expression(expr=_raw_expression(name, m.x, m.y, pyo, reciprocals))
    m.normalization_min = pyo.Param(initialize=low)
    m.normalization_range = pyo.Param(initialize=span)
    m.obj = pyo.Objective(expr=(m.raw_objective - m.normalization_min) / m.normalization_range)
    if verify_csv:
        m.grid_audit = _audit_model(m, Path(csv_dir) / f"{name}.csv", CSV_ATOL)
    return m


def build_all_grid_gdps(*, verify_csv=True, csv_dir=GRID_DIR):
    """Return 21 independent model instances, keyed by CSV stem."""
    return {name: build_grid_gdp(name, verify_csv=verify_csv, csv_dir=csv_dir) for name in GRID_NAMES}


def _integer_point(point):
    try:
        values = tuple(point)
        if len(values) != 2 or any(isinstance(v, bool) for v in values):
            raise ValueError
        numeric = tuple(float(v) for v in values)
        if any(not math.isfinite(v) or not v.is_integer() or not 0 <= v < GRID_SIZE for v in numeric):
            raise ValueError
        return tuple(int(v) for v in numeric)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Expected two integer grid indices in 0..30") from error


def fix_grid_point(model, point):
    """Fix a GDP in place to one CSV index pair and eliminate its disjunctions."""
    point = _integer_point(point)
    if not model.pick_x.active or not model.pick_y.active:
        raise ValueError("Expected an untransformed grid GDP")
    _assign_point(model, point)
    for k in model.I:
        model.Xchoice[k].indicator_var.fix(k == point[0])
        model.Ychoice[k].indicator_var.fix(k == point[1])
    model.x.fix()
    model.y.fix()
    if model.grid_name == "csendes":
        model.rx.fix()
        model.ry.fix()
    pyo.TransformationFactory("gdp.fix_disjuncts").apply_to(model)
    return model


def _read_reference(path):
    content = path.read_bytes()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    if not {"x", "y", "z_norm"} <= set(reader.fieldnames or ()):
        raise ValueError(f"Invalid CSV schema: {path}")
    values = {}
    for row in reader:
        point = _integer_point((row["x"], row["y"]))
        value = float(row["z_norm"])
        if point in values:
            raise ValueError(f"Duplicate CSV coordinate {point}: {path}")
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"Invalid normalized CSV value at {point}: {path}")
        values[point] = value
    expected = {(i, j) for i in range(GRID_SIZE) for j in range(GRID_SIZE)}
    if set(values) != expected:
        raise ValueError(f"Expected complete 31 x 31 grid (961 points): {path}")
    return values, hashlib.sha256(content).hexdigest()


def _minimizers(values, atol):
    minimum = min(values.values())
    return [list(point) for point in sorted(values) if values[point] - minimum <= atol]


def _audit_model(model, csv_path, atol):
    if not math.isfinite(atol) or atol <= 0:
        raise ValueError("atol must be finite and positive")
    reference, checksum = _read_reference(csv_path)
    actual = {}
    variables = [model.x, model.y]
    if model.grid_name == "csendes":
        variables += [model.rx, model.ry]
    initial = [v.value for v in variables]
    try:
        for point in sorted(reference):
            _assign_point(model, point)
            value = pyo.value(model.obj)
            if not math.isfinite(value):
                raise ValueError(f"Non-finite GDP objective: {model.grid_name} at {point}")
            actual[point] = value
    finally:
        for variable, value in zip(variables, initial):
            variable.set_value(value)
    worst = max(reference, key=lambda point: abs(actual[point] - reference[point]))
    error = abs(actual[worst] - reference[worst])
    if error > atol:
        raise ValueError(f"{model.grid_name}: CSV mismatch at {worst}: max error {error:.6g} > {atol}")
    csv_minimizers, model_minimizers = _minimizers(reference, atol), _minimizers(actual, atol)
    if csv_minimizers != model_minimizers:
        raise ValueError(f"{model.grid_name}: CSV and GDP minimizer sets differ at tolerance {atol}")
    csv_hits = [list(p) for p in sorted(reference) if reference[p] <= TARGET_TOLERANCE]
    model_hits = [list(p) for p in sorted(actual) if actual[p] <= TARGET_TOLERANCE]
    if csv_hits != model_hits:
        raise ValueError(f"{model.grid_name}: CSV and GDP target-hit sets differ")
    exact_csv = _minimizers(reference, 0.)
    exact_model = _minimizers(actual, 0.)
    return {
        "name": model.grid_name, "status": "passed", "points_checked": len(reference),
        "physical_bounds": list(BOUNDS[model.grid_name]),
        "normalization_min": pyo.value(model.normalization_min),
        "normalization_range": pyo.value(model.normalization_range),
        "max_abs_error": error, "worst_error_point": list(worst), "atol": atol,
        "csv_minimum": min(reference.values()), "model_minimum": min(actual.values()),
        "csv_minimizers": csv_minimizers, "model_minimizers": model_minimizers,
        "exact_csv_minimizers": exact_csv, "exact_model_minimizers": exact_model,
        "exact_float_minimizers_match": exact_csv == exact_model,
        "target_tolerance": TARGET_TOLERANCE, "target_points": len(csv_hits),
        "csv_sha256": checksum, "formula_note": FORMULA_NOTES.get(model.grid_name, ""),
    }


def audit_grid(name, *, csv_dir=GRID_DIR, atol=CSV_ATOL):
    """Exhaustively compare the symbolic GDP objective and minimizers with CSV.

    This is finite-grid enumeration, not a claim of convergence by an NLP or
    MINLP solver. Minimizers use the stated normalized absolute tolerance;
    exact floating-point argmins are reported separately.
    """
    model = build_grid_gdp(name, verify_csv=False)
    return _audit_model(model, Path(csv_dir) / f"{model.grid_name}.csv", atol)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List all 21 supported grids")
    validate = sub.add_parser("validate", help="Check every point and minimizer against CSV")
    validate.add_argument("--names", nargs="+", choices=GRID_NAMES, default=GRID_NAMES)
    validate.add_argument("--csv-dir", type=Path, default=GRID_DIR)
    validate.add_argument("--atol", type=float, default=CSV_ATOL)
    validate.add_argument("--output", type=Path, help="Optionally save the validation JSON")
    args = parser.parse_args(argv)
    if args.command == "list":
        print("\n".join(GRID_NAMES))
        return 0
    try:
        if len(set(args.names)) != len(args.names):
            raise ValueError("Choose distinct grid names")
        rows = [audit_grid(name, csv_dir=args.csv_dir, atol=args.atol) for name in args.names]
    except (ValueError, OSError) as error:
        parser.exit(2, f"{error}\n")
    report = {
        "verification": "exhaustive analytic GDP grid evaluation; no optimization solver invoked",
        "formula_source_commit": FORMULA_SOURCE_COMMIT,
        "formula_source_path": FORMULA_SOURCE_PATH,
        "models": len(rows), "points_checked": sum(r["points_checked"] for r in rows),
        "max_abs_error": max(r["max_abs_error"] for r in rows), "grids": rows,
    }
    rendered = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
