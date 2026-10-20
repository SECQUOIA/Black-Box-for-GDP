"""Original model construction and external-integer-to-NLP mapping."""

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import math
from time import perf_counter
from uuid import uuid4

import pyomo.environ as pyo
from pyomo.contrib.fbbt.fbbt import fbbt
from pyomo.common.errors import InfeasibleConstraintException
from pyomo.gdp import Disjunct, Disjunction

from ._sources import load_source, provenance, source_root


MODELS = {
    "cstr": ("dsda-gdp", "gdp/cstr/gdp_reactor.py", "build_cstrs"),
    "column": ("dsda-gdp", "gdp/column/gdp_column.py", "build_column"),
    "small_batch": ("dsda-gdp", "gdp/small_batch/gdp_small_batch.py", "build_small_batch"),
    "dynamic": ("ld-sda-dynamic", "models/nine_stage_dynamic_model_switching_nonlinear.py", "build_model"),
}


class LogicalInfeasibility(InfeasibleConstraintException):
    """A fixed configuration contradicts the original GDP's Boolean logic."""


def build_gdp(case, *, cstr_size=5):
    """Return a fresh, unfixed original GDP (Dynamic is not yet discretized)."""
    if case not in MODELS:
        raise ValueError(f"Unknown case {case!r}; choose from {tuple(MODELS)}")
    name, relative, function = MODELS[case]
    builder = load_source(name, relative)[function]
    if case == "cstr":
        if isinstance(cstr_size, bool) or int(cstr_size) != cstr_size or cstr_size < 1:
            raise ValueError("cstr_size must be a positive integer")
        return builder(NT=int(cstr_size))
    if case == "column":
        return builder(min_trays=8, max_trays=17, xD=0.95, xB=0.95)
    if case == "dynamic":
        return builder(mode_transfer=False)
    return builder()


def integer_point(point):
    values = tuple(float(x) for x in point)
    if any(not math.isfinite(x) or abs(x - round(x)) > 1e-8 for x in values):
        raise ValueError("Coordinates must be finite integers (tolerance 1e-8)")
    return tuple(round(x) for x in values)


def _check_bounds(point, lower, upper):
    if len(point) != len(lower):
        raise ValueError(f"Expected {len(lower)} coordinates, received {len(point)}")
    if any(not lo <= x <= hi for x, lo, hi in zip(point, lower, upper)):
        raise ValueError(f"Point {point} outside bounds {lower} .. {upper}")


def initialization_info(case, size, policy):
    """Describe the cold start without constructing or solving an NLP."""
    if policy not in {"auto", "saved", "default"}:
        raise ValueError("initialization must be auto, saved, or default")
    label = f"cstr_{size}" if case == "cstr" else (
        "column_17" if case == "column" else case
    )
    relative = f"gdp/dsda/{label}_initialization.json"
    if case == "dynamic" or policy == "default":
        if policy == "saved":
            raise FileNotFoundError("No saved Dynamic initialization is supplied")
        return "constructor_defaults", []
    path = source_root("dsda-gdp") / relative
    if not path.is_file():
        if policy == "saved":
            raise FileNotFoundError(f"No saved initialization: {path}")
        return "constructor_defaults (no upstream saved initialization)", []
    serializer_file = "gdp/dsda/model_serializer.py"
    return relative, [relative, serializer_file]


def _initialize(m, case, size, policy):
    initialized_from, files = initialization_info(case, size, policy)
    if not files:
        return initialized_from, files
    path = source_root("dsda-gdp") / initialized_from
    serializer_file = "gdp/dsda/model_serializer.py"
    serializer = load_source("dsda-gdp", serializer_file)
    serializer["from_json"](m, fname=str(path), wts=serializer["StoreSpec"].value())
    return initialized_from, files


def _fix_static(m, case, point):
    helper_file = "gdp/dsda/dsda_functions.py"
    functions = ("external_ref", "get_external_information")
    helpers = load_source("dsda-gdp", helper_file, functions)
    main_file = f"main_{case}.py"
    logic_name = "problem_logic_batch" if case == "small_batch" else f"problem_logic_{case}"
    logic = load_source("dsda-gdp", main_file, (logic_name,))[logic_name]
    if case == "cstr":
        reference = {m.YF: m.N, m.YR: m.N}
    elif case == "column":
        reference = {m.YB: m.intTrays, m.YR: m.intTrays}
    else:
        reference = {m.Y: m.k}
    reformulation, _, lower, upper = helpers["get_external_information"](m, reference)
    _check_bounds(point, tuple(lower.values()), tuple(upper.values()))
    # Preserve logical restrictions fixed by the original GDP constructor.
    fixed_booleans = [(v, pyo.value(v)) for v in
                      m.component_data_objects(pyo.BooleanVar) if v.fixed]
    logical_constraints = list(m.component_data_objects(pyo.LogicalConstraint, active=True))
    helpers["external_ref"](m, list(point), logic, reformulation)
    # The upstream Column links YP to tray indicators, but Pyomo does not
    # synchronize their Boolean values automatically. Do not ask Pyomo to
    # materialize unused auxiliary binaries while checking this logic.
    if case == "column":
        for tray in m.conditional_trays:
            m.YP[tray].set_value(pyo.value(m.tray[tray].indicator_var))
    if any(pyo.value(v) != value for v, value in fixed_booleans):
        raise LogicalInfeasibility("Point contradicts original fixed GDP logic")
    for constraint in logical_constraints:
        if pyo.value(constraint.body, exception=False) is not True:
            raise LogicalInfeasibility(f"Unsatisfied GDP logic: {constraint.name}")
    return [helper_file, main_file]


def _discretize_dynamic(m):
    pyo.TransformationFactory("dae.collocation").apply_to(
        m, nfe=30, ncp=3, scheme="LAGRANGE-RADAU"
    )
    # Upstream benchmark workaround: expand disjunct constraints onto DAE mesh.
    for disjunct in m.component_data_objects(Disjunct):
        for constraint in disjunct.component_objects(pyo.Constraint):
            constraint._constructed = False
            constraint.construct()
    for var in m.component_data_objects(pyo.Var, descend_into=True):
        if "dxdt" in var.name:
            var.setlb(-300)
            var.setub(300)


@dataclass
class DynamicTemplate:
    model: object
    preparation: dict


@lru_cache(maxsize=1)
def dynamic_template():
    """Discretize once per process; timed point evaluations clone this model.

    The template is never fixed or solved, so IPOPT iterates cannot leak into
    the starting values of another external integer point.
    """
    started = perf_counter()
    m = build_gdp("dynamic")
    built = perf_counter()
    _discretize_dynamic(m)
    finished = perf_counter()
    return DynamicTemplate(m, {
        "preparation_id": uuid4().hex, "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "once_per_process", "model_build_wall_s": built - started,
        "dae_wall_s": finished - built, "total_preparation_wall_s": finished - started,
        "included_in_point_total_wall_s": False,
    })


def _fix_dynamic(m, point):
    _check_bounds(point, (1, 2), (9, 9))
    if not (point[0] < point[1] or point == (9, 9)):
        raise LogicalInfeasibility("Dynamic requires x < y or x = y = 9")
    for stage in m.stage:
        selected = 1 if stage <= point[0] else (2 if stage <= point[1] else 3)
        for mode in m.mode:
            m.stage_mode[stage, mode].indicator_var.fix(mode == selected)
    pyo.TransformationFactory("core.logical_to_linear").apply_to(m)
    pyo.TransformationFactory("gdp.fix_disjuncts").apply_to(m)


@dataclass
class PreparedNLP:
    model: object
    point: tuple
    metadata: dict
    timings: dict
    constraints: list


def prepare_nlp(case, point, *, cstr_size=5, initialization="auto"):
    """Build a fresh cold-start subproblem; never consult the objective tables."""
    template = dynamic_template() if case == "dynamic" else None
    started = perf_counter()
    point = integer_point(point)
    m = template.model.clone() if template else build_gdp(case, cstr_size=cstr_size)
    initialized_from, files = _initialize(m, case, cstr_size, initialization)
    if case == "dynamic":
        _fix_dynamic(m, point)
    else:
        files += _fix_static(m, case, point)
    constraints = list(m.component_data_objects(pyo.Constraint, active=True, descend_into=True))
    name, relative, _ = MODELS[case]
    metadata = {
        "case": case, "cstr_size": cstr_size if case == "cstr" else None,
        "initialization": initialized_from, "warm_start": False,
        "source": provenance(name, [relative, *files]),
        "discretization": {"nfe": 30, "ncp": 3, "scheme": "LAGRANGE-RADAU",
                           "derivative_bounds": [-300, 300],
                           "reuse": "clone_once_per_process_template"} if case == "dynamic" else None,
        "preprocessing": "fbbt+constraint_propagation" if case == "cstr"
                         else ("none" if case == "dynamic" else "fbbt"),
    }
    if template:
        metadata["preparation_id"] = template.preparation["preparation_id"]
    setup = perf_counter() - started
    preprocess_start = perf_counter()
    if case != "dynamic":
        fbbt(m)
    if case == "cstr":
        for name in ["detect_fixed_vars", "propagate_fixed_vars", "remove_zero_terms",
                     "propagate_zero_sum", "constraints_to_var_bounds",
                     "detect_fixed_vars", "propagate_zero_sum"]:
            pyo.TransformationFactory("contrib." + name).apply_to(m)
        pyo.TransformationFactory("contrib.deactivate_trivial_constraints").apply_to(
            m, tmp=False, ignore_infeasible=False
        )
    unfixed = [v.name for v in m.component_data_objects(pyo.Var, active=True)
               if (v.is_integer() or v.is_binary()) and not v.fixed]
    if unfixed or list(m.component_data_objects(Disjunction, active=True)):
        raise RuntimeError(f"GDP was not fully fixed to an NLP: {unfixed}")
    return PreparedNLP(m, point, metadata, {
        "setup_wall_s": setup, "preprocess_wall_s": perf_counter() - preprocess_start,
    }, constraints)
