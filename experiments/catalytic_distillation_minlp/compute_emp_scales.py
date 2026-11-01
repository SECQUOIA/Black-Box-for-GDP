"""Compute the scales s of the disjunct constraints of the EMP column model.

  GAMS_EXE=/path/to/gams python experiments/catalytic_distillation_minlp/compute_emp_scales.py [OUTPUT]

GAMS CONVERT writes emp_model_corrected.gms, with every scale equal to 1, as a scalar
Pyomo model.  FBBT over the global constraints, which hold for every configuration,
tightens the variable bounds.  For every disjunct equation with residual h = lhs - rhs,
interval arithmetic over these bounds gives h in [lo, hi], and s = 1.01*max(|lo|, |hi|).
The scaled constraint h/s lies in [-1, 1] at every feasible point, so M = 1 is a valid
Big-M for every disjunct constraint, and the residual variable r = h/s of a nonlinear
disjunct equation gets the bounds [lo/s, hi/s].  The FBBT bounds of the variables in the
linear disjunct constraints are written too, so that the scaled constraints lie in [-1, 1]
over the bounds of the model itself.

The script writes OUTPUT (default gdp_models/catalytic_distillation/emp_scales.gms) and repeats the
interval computation with the scales in place, which must give |h/s| <= 1 everywhere.
Requires GAMS (with CONVERT) and Pyomo.
"""

import os
import re
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

from pyomo.contrib.fbbt.fbbt import compute_bounds_on_expr, fbbt
from pyomo.core.expr.visitor import identify_variables
from pyomo.repn import generate_standard_repn

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_emp  # noqa: E402

GAMS = os.environ.get("GAMS_EXE", "gams")
SCALES = make_emp.FOLDER / "emp_scales.gms"
INIT = make_emp.FOLDER / "init"
SAFETY = 1.01


def convert(workdir, scales=None):
    """Write the EMP model as a scalar Pyomo model; return the model and the GAMS names."""
    lines = [f'$include "{make_emp.TARGET}"']
    if scales:
        lines.append(f'$include "{scales}"')
    lines += ["$onecho > convert.opt", "Pyomo pyomo_model.py", "Dict dict.txt", "$offecho",
              f'execute_loadpoint "{INIT}";', "DSDA.optfile = 1;", "option minlp = convert;",
              "solve DSDA using minlp minimizing zobj;"]
    (workdir / "convert_driver.gms").write_text("\n".join(lines) + "\n")
    subprocess.run([GAMS, "convert_driver.gms", "lo=2"], cwd=workdir, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    model = runpy.run_path(str(workdir / "pyomo_model.py"))["m"]
    names = {}
    for line in (workdir / "dict.txt").read_text().splitlines():
        m = re.match(r"\s+([exbi]\d+)\s+(\S+)$", line)
        if m:
            names[m.group(1)] = m.group(2)
    by_name = {}
    for component in list(model.component_data_objects(ctype=None, descend_into=True)):
        local = component.local_name
        if local in names:
            by_name[names[local]] = component
    return model, by_name


def family(name):
    return name.split("(", 1)[0]


def residual_intervals(model, by_name):
    """Interval of (lhs - rhs)/s for every disjunct equation instance, after FBBT.

    Without scales (s = 1) this is the interval of h = lhs - rhs.  Also returns the bounds
    that FBBT implies for the variables of the linear disjunct constraints, where tighter.
    """
    disjunct = set(make_emp.FAMILIES) | {f"{f}_ge" for f in make_emp.FAMILIES}
    for name, component in by_name.items():
        if family(name) in disjunct:
            component.deactivate()
    variables = {id(v): name for name, v in by_name.items() if not hasattr(v, "body")}
    source = {name: (v.lb, v.ub) for name, v in by_name.items() if not hasattr(v, "body")}
    fbbt(model)
    implied = {}
    intervals = {}
    for name, component in by_name.items():
        fam = family(name)
        if fam in make_emp.LIFTED and name.startswith(f"r_{fam}("):
            continue
        if fam.startswith("def_") and fam[4:] in make_emp.LIFTED:
            # s*r = h, so with r fixed at zero the body is c*0 + q and h/s = r = (rhs - q)/c.
            r = by_name[f"r_{fam[4:]}" + name[len(fam):]]
            repn = generate_standard_repn(component.body, compute_values=True)
            coef = dict(zip([id(v) for v in repn.linear_vars], repn.linear_coefs))[id(r)]
            saved = r.lb, r.ub
            r.fix(0)
            lo, hi = compute_bounds_on_expr(component.body)
            r.unfix()
            r.setlb(saved[0])
            r.setub(saved[1])
            if lo is None or hi is None:
                intervals[fam[4:] + name[len(fam):]] = (lo, hi, coef)
                continue
            h = sorted([(component.upper - hi) / coef, (component.upper - lo) / coef])
            intervals[fam[4:] + name[len(fam):]] = (h[0], h[1], coef)
        elif fam in make_emp.FAMILIES and fam not in make_emp.LIFTED:
            for v in identify_variables(component.body, include_fixed=False):
                vname = variables[id(v)]
                if v.is_binary() or vname in implied:
                    continue
                lo0, hi0 = source[vname]
                lo1 = None if v.lb is None else v.lb - 1e-6 * max(1.0, abs(v.lb))
                hi1 = None if v.ub is None else v.ub + 1e-6 * max(1.0, abs(v.ub))
                lo1 = lo1 if lo1 is not None and (lo0 is None or lo1 > lo0) else None
                hi1 = hi1 if hi1 is not None and (hi0 is None or hi1 < hi0) else None
                if lo1 is not None or hi1 is not None:
                    implied[vname] = (lo1, hi1)
            lo, hi = compute_bounds_on_expr(component.body)
            bound = component.upper if component.upper is not None else component.lower
            intervals[name] = (None if lo is None else lo - bound, None if hi is None else hi - bound, None)
    unbounded = sorted(name for name, (lo, hi, _) in intervals.items()
                       if lo is None or hi is None or abs(lo) == float("inf") or abs(hi) == float("inf"))
    if unbounded:
        raise ValueError(f"{len(unbounded)} unbounded residuals, e.g. {unbounded[:8]}")
    return intervals, implied


def gams_index(name):
    if "(" not in name:
        return name, ""
    fam, rest = name.split("(", 1)
    return fam, "(" + ",".join(f"'{i}'" for i in rest.rstrip(")").split(",")) + ")"


def write_scales(intervals, implied, path):
    lines = ["* Scales of the disjunct constraints of emp_model_corrected.gms, written by",
             "* experiments/catalytic_distillation_minlp/compute_emp_scales.py; do not edit by hand.",
             "* Bounds implied by the global constraints (FBBT) for the variables of linear disjunct constraints."]
    for name in sorted(implied):
        var, index = gams_index(name)
        lo, hi = implied[name]
        if lo is not None:
            lines.append(f"{var}.lo{index}={lo:.12e};")
        if hi is not None:
            lines.append(f"{var}.up{index}={hi:.12e};")
    lines.append("* s bounds |lhs - rhs| at every feasible point; r = (lhs - rhs)/s lies in [r.lo, r.up].")
    for name in sorted(intervals, key=lambda n: (make_emp.FAMILIES.index(family(n)), n)):
        lo, hi, _ = intervals[name]
        s = SAFETY * max(abs(lo), abs(hi)) or 1.0
        fam, index = gams_index(name)
        lines.append(f"s_{fam}{index}={s:.12e};")
        if fam in make_emp.LIFTED:
            lines.append(f"r_{fam}.lo{index}={lo / s - 1e-9:.12e};")
            lines.append(f"r_{fam}.up{index}={hi / s + 1e-9:.12e};")
    path.write_text("\n".join(lines) + "\n")


def check(intervals, by_name):
    """With the scales in place, every scaled residual must lie in [-1, 1]."""
    worst = 0.0
    for name, (lo, hi, _) in intervals.items():
        fam = family(name)
        worst = max(worst, abs(lo), abs(hi))
        if fam in make_emp.LIFTED:
            r = by_name[f"r_{fam}" + name[len(fam):]]
            # FBBT may have tightened r onto the interval itself.
            assert -1 <= r.lb <= lo + 1e-9 and hi - 1e-9 <= r.ub <= 1, (name, r.lb, lo, hi, r.ub)
    return worst


def summary(intervals):
    rows = {}
    for name, (lo, hi, _) in intervals.items():
        s = SAFETY * max(abs(lo), abs(hi)) or 1.0
        fam = family(name)
        count, smin, smax = rows.get(fam, (0, float("inf"), 0.0))
        rows[fam] = (count + 1, min(smin, s), max(smax, s))
    return rows


def main(output=SCALES):
    output = Path(output).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        first = Path(tmp) / "unscaled"
        first.mkdir()
        intervals, implied = residual_intervals(*convert(first))
        write_scales(intervals, implied, output)
        second = Path(tmp) / "scaled"
        second.mkdir()
        model, by_name = convert(second, output)
        worst = check(residual_intervals(model, by_name)[0], by_name)
    print(f"wrote {output}: {len(intervals)} disjunct equations, "
          f"{len(implied)} implied variable bounds")
    for fam, (count, smin, smax) in summary(intervals).items():
        print(f"  {fam:26s} {count:4d}  s in [{smin:.3g}, {smax:.3g}]")
    print(f"largest |h/s| with the scales in place: {worst:.6f}")
    assert worst <= 1.0, worst
    return worst


if __name__ == "__main__":
    main(*sys.argv[1:])
