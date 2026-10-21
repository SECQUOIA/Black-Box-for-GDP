"""Recreate the fixed NLP inventory and NL serialization without invoking a solver."""

import argparse
from collections import Counter
from pathlib import Path

from pyomo.core.expr.visitor import identify_variables
from pyomo.repn.standard_repn import generate_standard_repn

from gdp_models.comparison import DESCEND, pyo
from review_diagnostics import feasibility as f
from review_diagnostics.common import save


def reproduce(directory, output):
    output.mkdir(parents=True, exist_ok=False)
    model, _, _ = f.verify_input(directory)
    nlp = f.prepare_fixed_nlp(model)
    variables = list(nlp.component_data_objects(pyo.Var, descend_into=DESCEND))
    constraints = list(nlp.component_data_objects(pyo.Constraint, active=True))
    equalities = [c for c in constraints if c.equality]
    rows = []
    for constraint in equalities:
        free = list(identify_variables(constraint.body, include_fixed=False))
        representation = generate_standard_repn(constraint.body)
        rows.append({
            "name": constraint.name,
            "free_variables": [v.name for v in free],
            "is_linear": representation.is_linear(),
            "value": pyo.value(constraint.body),
            "rhs": pyo.value(constraint.lower),
            "expression": str(constraint.expr),
        })
    nlp.write(str(output / "fixed_nlp.nl"), io_options={"symbolic_solver_labels": True})
    save(output / "equalities.json", rows)
    save(output / "counts.json", {
        "variables_total": len(variables),
        "free_variables": sum(not v.fixed for v in variables),
        "active_constraints": len(constraints),
        "active_equalities": len(equalities),
        "equalities_with_free_variables": sum(bool(c["free_variables"]) for c in rows),
        "equality_groups": dict(Counter(c.parent_component().local_name for c in equalities)),
        "solver_calls_in_this_inspection": 0,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reproduce(args.directory.resolve(), args.output.resolve())
