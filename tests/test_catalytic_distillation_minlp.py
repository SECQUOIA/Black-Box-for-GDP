"""Checks of the MINLP forms of the catalytic distillation column: product, Big-M, and convex hull."""
import csv
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "experiments/catalytic_distillation_minlp"
MODEL = ROOT / "gdp_models/catalytic_distillation"
RESULTS = ROOT / "results/catalytic_distillation_minlp_20261101"
sys.path.insert(0, str(HERE))
import make_emp  # noqa: E402
import make_minlp  # noqa: E402

GAMS = os.environ.get("GAMS_EXE") or shutil.which("gams")
BEST = (8, 8, 12, 17, 17, 21)
BEST_ZOBJ = 24895.552861


def test_committed_models_are_the_generator_output():
    assert make_minlp.build(make_minlp.SOURCE.read_text()) == make_minlp.TARGET.read_text()
    assert make_emp.build(make_emp.SOURCE.read_text()) == make_emp.TARGET.read_text()


def emp_disjunctions():
    """Equations that solve_emp.gms puts into each disjunction, by indicator and term."""
    text = (MODEL / "solve_emp.gms").read_text()
    body = text[text.index("loop(inner(Net),"):text.index("putclose emp;")]
    found = {}
    for block in body.split("put 'disjunction ' ")[1:]:
        indicator = re.match(r"(\w+)\(Net\)", block).group(1)
        on, _, off = block.partition("' else'")
        found[(indicator, True)] = set(re.findall(r"' ' (\w+)\(", on))
        found[(indicator, False)] = set(re.findall(r"' ' (\w+)\(", off))
    return found


def test_every_disjunct_constraint_is_in_its_disjunction():
    emp = make_emp.TARGET.read_text()
    equalities = {name for name in make_emp.FAMILIES if f"equation {name}_ge(" in emp}
    found = emp_disjunctions()
    assert set(found) == set(make_emp.DISJUNCTS)
    for key, names in make_emp.DISJUNCTS.items():
        assert found[key] == set(names) | {f"{name}_ge" for name in names if name in equalities}, key


def test_disjunct_constraints_are_linear_in_the_emp_model():
    emp = make_emp.TARGET.read_text()
    for name in make_emp.LIFTED:
        assert re.search(rf"^def_{name}\(", emp, flags=re.M), name
        assert re.search(rf"^{name}\([^)]*\)(\$\(.*?\))?\.\. r_{name}\([^)]*\)=[lg]=0;", emp, flags=re.M), name
    for name in set(make_emp.FAMILIES) - set(make_emp.LIFTED):
        assert re.search(rf"^{name}\([^)]*\)(\$\(.*?\))?\.\. \(.*\)/s_{name}\([^)]*\)=[lg]=0;", emp, flags=re.M), name


def test_scales_cover_every_disjunct_equation():
    text = (MODEL / "emp_scales.gms").read_text()
    scales = re.findall(r"^s_(\w+)\(([^)]*)\)=(\S+);", text, flags=re.M)
    assert {name for name, _, _ in scales} == set(make_emp.FAMILIES)
    assert len(scales) == len({(name, index) for name, index, _ in scales}) == 1058
    assert all(float(value) > 0 for _, _, value in scales)
    bounds = re.findall(r"^r_(\w+)\.(lo|up)\(([^)]*)\)=(\S+);", text, flags=re.M)
    lifted = {(name, index) for name, index, _ in scales if name in make_emp.LIFTED}
    assert {(name, index) for name, _, index, _ in bounds} == lifted
    assert len(bounds) == 2 * len(lifted)
    assert all(-1 <= float(value) <= 1 for *_, value in bounds)


@pytest.mark.skipif(not GAMS, reason="GAMS not available")
def test_scales_are_reproduced_and_bound_every_scaled_residual(tmp_path):
    pytest.importorskip("pyomo")
    import compute_emp_scales

    compute_emp_scales.GAMS = GAMS
    assert compute_emp_scales.main(tmp_path / "emp_scales.gms") <= 1
    assert (tmp_path / "emp_scales.gms").read_text() == (MODEL / "emp_scales.gms").read_text()


@pytest.mark.skipif(not GAMS, reason="GAMS not available")
@pytest.mark.parametrize("reform", ["bigm", "chull"])
def test_fixed_best_design_matches_the_gdp_form(tmp_path, reform):
    args = [f"--{key}={value}" for key, value in zip(["f1", "c1", "c2", "c3", "f2", "b"], BEST)]
    subprocess.run([GAMS, str(MODEL / "solve_emp.gms"), f"--model={MODEL / 'emp_model_corrected.gms'}",
                    f"--init={MODEL / 'init'}", f"--reform={reform}", "--solver=sbb", "--reslim=600",
                    f"--out={tmp_path / 'result.txt'}", *args, "lo=0"], cwd=tmp_path, check=True)
    result = dict(item.split("=", 1) for item in (tmp_path / "result.txt").read_text().split())
    assert result["modelstat"] == "2" and abs(float(result["zobj"]) - BEST_ZOBJ) < 1e-5


def test_validation_agrees_on_the_feasible_designs():
    rows = list(csv.DictReader((RESULTS / "validation/validation.csv").open()))
    by_config = {}
    for row in rows:
        by_config.setdefault(tuple(int(row[k]) for k in ["f1", "c1", "c2", "c3", "f2", "b"]), {})[row["form"]] = row
    assert len(by_config) == 9 and all(set(forms) == {"gdp", "product", "bigm", "chull"} for forms in by_config.values())
    for config, forms in by_config.items():
        feasible = {form: row["modelstat"] == "2" for form, row in forms.items()}
        assert len(set(feasible.values())) == 1, config
        if feasible["gdp"]:
            for form in ["bigm", "chull"]:
                assert abs(float(forms[form]["zobj"]) - float(forms["gdp"]["zobj"])) < 1e-5, (config, form)
    assert abs(float(by_config[BEST]["gdp"]["zobj"]) - BEST_ZOBJ) < 1e-6


def test_solver_summary_matches_the_runs():
    rows = list(csv.DictReader((RESULTS / "summary.csv").open()))
    assert {(row["form"], row["solver"]) for row in rows} == {
        (form, solver) for form in ["product", "bigm", "chull"] for solver in ["dicopt", "sbb", "baron", "scip"]}
    for row in rows:
        text = (RESULTS / row["form"] / row["solver"] / "result.txt").read_text()
        result = dict(item.split("=", 1) for item in text.split() if "=" in item)
        assert (row["modelstat"], row["solvestat"], row["zobj"]) == (result["modelstat"], result["solvestat"], result["zobj"])
    # Model status 1, 2, 7, or 8 returns a feasible design; none comes within 15% of the reference.
    feasible = [row for row in rows if row["modelstat"] in {"1", "2", "7", "8"}]
    assert [(row["form"], row["solver"]) for row in feasible] == [("product", "sbb")]
    assert all(float(row["zobj"]) > 1.15 * BEST_ZOBJ for row in feasible)
