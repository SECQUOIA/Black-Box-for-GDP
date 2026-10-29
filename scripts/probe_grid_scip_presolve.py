"""Solver-free local replay of returned Grid-GDP missed/neighboring points."""
import argparse
import hashlib
import importlib
import importlib.metadata
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyomo.environ as pyo  # noqa: E402
from gdp_models.grid import build_grid_gdp  # noqa: E402
from pyomo.contrib.gdpopt import create_oa_subproblems as create  # noqa: E402
from pyomo.contrib.gdpopt.solve_subproblem import preprocess_subproblem  # noqa: E402
from pyomo.contrib.gdpopt.util import move_nonlinear_objective_to_constraints  # noqa: E402
from pyomo.contrib.fbbt.fbbt import fbbt  # noqa: E402
from pyomo.contrib.fbbt import interval  # noqa: E402


def setup(name, point):
    model = build_grid_gdp(name)
    fbbt(model)
    util = create.add_util_block(model)
    create.add_disjunct_list(util)
    create.add_boolean_variable_lists(util)
    create.add_algebraic_variable_list(util)
    move_nonlinear_objective_to_constraints(util, logging.getLogger("probe"))
    model, util = create.get_subproblem(model, util)
    for choices, selected in zip((model.Xchoice, model.Ychoice), point):
        for index, disjunct in choices.items():
            disjunct.indicator_var.fix(index == selected)
            if index != selected:
                disjunct.deactivate()
    return model, util


def probe(name, point):
    config = pyo.SolverFactory("gdpopt.gloa").config
    model, util = setup(name, point)
    inverses = []
    originals = {n: getattr(interval, n) for n in ("asin", "acos")}

    def wrap(name):
        def traced(*args):
            output = originals[name](*args)
            inverses.append({"function": name, "input": list(args), "output": list(output)})
            return output
        return traced

    error = None
    try:
        for fn in originals:
            setattr(interval, fn, wrap(fn))
        fbbt(model, integer_tol=config.integer_tolerance,
             feasibility_tol=config.constraint_tolerance, max_iter=config.max_fbbt_iterations)
    except Exception as exception:
        error = f"{type(exception).__name__}: {exception}"
    finally:
        for fn, original in originals.items():
            setattr(interval, fn, original)
    model, util = setup(name, point)
    with preprocess_subproblem(util, config) as allowed:
        returned = bool(allowed)
    return {"grid_name": name, "point": list(point), "fbbt_error": error,
            "presolve_allows_solver": returned, "inverse_propagation": inverses,
            "optimization_solver_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if importlib.metadata.version("pyomo") != "6.10.0":
        raise RuntimeError("This historical replay requires Pyomo 6.10.0")
    cases = {"michalewicz": [(21,15), (22,15)], "shubert": [(17,22), (17,21)],
             "holder_table": [(3,1), (27,1), (0,1)]}
    sources = {}
    for name in ("pyomo.contrib.fbbt.fbbt", "pyomo.contrib.fbbt.interval",
                 "pyomo.contrib.gdpopt.solve_subproblem"):
        module = importlib.import_module(name)
        sources[name] = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    report = {"python": sys.version, "pyomo": "6.10.0", "sources_sha256": sources,
              "optimization_solver_calls": 0,
              "scope": "Local common GDPopt preprocessing only; not a new Dantzig execution or full candidate/no-good trace",
              "results": [probe(name, point) for name, points in cases.items() for point in points]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps([{k:v for k,v in r.items() if k != "inverse_propagation"}
                      for r in report["results"]], indent=2))


if __name__ == "__main__":
    main()
