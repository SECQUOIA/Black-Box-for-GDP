"""Reproduce the Dynamic Hull witness audit without invoking an optimizer."""
import ast
from collections import defaultdict
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts import analyze_process_scip_return as prior  # noqa: E402
from scripts import analyze_process_scip_four_return as four  # noqa: E402

require, sha, save = prior.require, prior.digest, prior.save_json
TOL = prior.TOLERANCE
ARCHIVE = ROOT / "results/archives/process_scip_minlp_20261026_result.zip"
REVISION = "ed40a19c33725e0ee8c5403e66768eb6b27072b2"


def tracked_hashes():
    # Keep the protection set stable after this diagnostic is committed.
    entries = subprocess.check_output(["git", "ls-tree", "-r", "-z", REVISION], cwd=ROOT).decode().split("\0")
    files = [entry.split("\t", 1)[1] for entry in entries if entry and entry.split("\t", 1)[0].split()[1] == "blob"]
    return {name: sha((ROOT / name).read_bytes()) for name in files}


def algebraic_check(model):
    import pyomo.environ as pyo
    from pyomo.gdp import Disjunct
    maxima = {"bounds": 0., "integrality": 0., "constraints": 0.}
    worst = dict.fromkeys(maxima)
    counts = defaultdict(int)
    top = []

    def observe(kind, value, name):
        require(math.isfinite(value), "Nonfinite residual: " + name)
        if value > maxima[kind]:
            maxima[kind], worst[kind] = value, name

    for var in model.component_data_objects(pyo.Var, descend_into=(pyo.Block, Disjunct)):
        value = pyo.value(var)
        require(value is not None and math.isfinite(value), "Missing transformed variable: " + var.name)
        counts["variables"] += 1
        observe("bounds", max(0., pyo.value(var.lb) - value if var.has_lb() else 0.,
                              value - pyo.value(var.ub) if var.has_ub() else 0.), var.name)
        if var.is_integer():
            counts["integer_variables"] += 1
            observe("integrality", abs(value - round(value)), var.name)
    for con in model.component_data_objects(pyo.Constraint, active=True):
        body = pyo.value(con.body)
        residual = max(0., pyo.value(con.lower) - body if con.has_lb() else 0.,
                       body - pyo.value(con.upper) if con.has_ub() else 0.)
        counts["constraints"] += 1
        observe("constraints", residual, con.name)
        top.append({"name": con.name, "violation": residual})
    return {"passes_1e_5": max(maxima.values()) <= TOL, "objective": float(pyo.value(model.obj)),
            "counts": dict(counts), "maxima": maxima, "worst": worst,
            "largest_constraint_residuals": sorted(top, key=lambda r: -r["violation"])[:10]}


def original_snapshot(model):
    import pyomo.environ as pyo
    from pyomo.gdp import Disjunct
    return {"objective_expression": str(model.obj.expr), "objective_sense": str(model.obj.sense),
            "variables": {v.name: {"bounds": [v.lb, v.ub], "initial": v.value, "fixed": v.fixed,
                                    "domain": str(v.domain)}
                          for v in model.component_data_objects(pyo.Var, descend_into=(pyo.Block, Disjunct))}}


def lift(model, original_names, solution):
    """Use Hull's public maps, including shared complementary copies.

    Each copy equals the source value times the sum of indicators mapped to it.
    For a branch copy this is y_d*x, and for a complementary copy it is
    (1-sum(y_d for branches containing x))*x under the original XOR constraint.
    """
    import pyomo.environ as pyo
    from pyomo.gdp import Disjunction, Disjunct
    hull = pyo.TransformationFactory("gdp.hull")
    variables = list(model.component_data_objects(pyo.Var, descend_into=(pyo.Block, Disjunct)))
    originals = [v for v in variables if v.name in original_names]
    require({v.name for v in originals} == set(solution["variables"]), "Incomplete original vector")
    for var in variables:
        if var.name in original_names:
            if var.fixed:
                require(abs(var.value - solution["variables"][var.name]) <= TOL, "Changed fixed variable")
            var.set_value(solution["variables"][var.name], skip_validation=True)
        else:
            require(not var.fixed, "Unexpected fixed auxiliary variable")
            var.set_value(None)
    rows = {}
    for disjunction in model.component_data_objects(Disjunction, active=None):
        copies = {}
        for disjunct in disjunction.disjuncts:
            if disjunct.transformation_block is None:
                require(pyo.value(disjunct.binary_indicator_var) == 0, "Untransformed selected branch")
                continue
            for source in originals:
                copy = hull.get_disaggregated_var(source, disjunct, raise_exception=False)
                if copy is None:
                    continue
                require(copy is not source, "Local-variable case needs explicit separate treatment")
                require(hull.get_src_var(copy) is source, "Hull reverse map mismatch")
                entry = copies.setdefault(copy.name, [copy, source, []])
                entry[2].append(disjunct)
        for name, (copy, source, branches) in copies.items():
            require(name not in rows, "Unexpected cross-disjunction copy")
            weight = sum(pyo.value(d.binary_indicator_var) for d in branches)
            copy.set_value(weight * pyo.value(source), skip_validation=True)
            rows[name] = {"auxiliary": name, "source": source.name, "disjunction": disjunction.name,
                          "indicator_branches": [d.name for d in branches], "weight": weight,
                          "source_value": pyo.value(source), "value": pyo.value(copy),
                          "rule": "complementary" if copy.parent_component().local_name == "_disaggregatedVars" else "branch"}
    require(set(rows) == {v.name for v in variables if v.name not in original_names}, "Incomplete Hull auxiliary lift")
    return list(rows.values())


def gams_check(text, model, symbol_map):
    """Numerically evaluate the archived GAMS algebra, without GAMS or a solver.

    Only arithmetic, names, constants, power and exp are accepted by the parser.
    Declared positive/binary domains and explicit bound assignments are checked.
    """
    import pyomo.environ as pyo
    values = {name: float(pyo.value(obj)) for name, obj in symbol_map.bySymbol.items()
              if obj.ctype is pyo.Var}
    values["GAMS_OBJECTIVE"] = float(pyo.value(model.obj))
    safe_types = (ast.Expression, ast.Constant, ast.Name, ast.Load, ast.BinOp, ast.UnaryOp,
                  ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.UAdd, ast.USub, ast.Call)

    def evaluate(expr):
        tree = ast.parse(expr.strip(), mode="eval")
        require(all(isinstance(node, safe_types) for node in ast.walk(tree)), "Unsupported GAMS expression")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                require(isinstance(node.func, ast.Name) and node.func.id in {"power", "exp"}
                        and not node.keywords, "Unsupported GAMS function")
            if isinstance(node, ast.Name):
                require(node.id in values or node.id in {"power", "exp"}, "Unknown GAMS symbol")
        result = eval(compile(tree, "<archived-gams-expression>", "eval"),
                      {"__builtins__": {}, "power": pow, "exp": math.exp}, values)
        require(math.isfinite(result), "Nonfinite GAMS expression")
        return result

    bounds, binary = {}, set()
    for match in re.finditer(r"(?m)^(BINARY |POSITIVE |FREE )?VARIABLES\s*\n(.*?);", text, re.S):
        kind, names = match.groups()
        for name in names.split():
            require(name in values and name not in bounds, "GAMS declaration mismatch")
            bounds[name] = [0. if kind in {"BINARY ", "POSITIVE "} else -math.inf,
                            1. if kind == "BINARY " else math.inf]
            if kind == "BINARY ":
                binary.add(name)
    require(set(bounds) == set(values), "Incomplete GAMS declarations")
    assignments = re.findall(r"(?m)^(x\d+)\.(lo|up|fx|l) = (.*?);$", text)
    for name, kind, expr in assignments:
        val = evaluate(expr)
        if kind == "fx":
            bounds[name] = [val, val]
        elif kind in {"lo", "up"}:
            bounds[name][0 if kind == "lo" else 1] = val
    bound_rows = [(max(0., lower-values[name], values[name]-upper), name)
                  for name, (lower, upper) in bounds.items()]
    equations = re.findall(r"(?m)^(c\d+(?:_lo|_hi)?)\.\.\s*(.*?)\s*=(e|l|g)=\s*(.*?)\s*;\s*$", text)
    require(len(equations) == text.count(".."), "Unsupported or omitted GAMS equation")
    residuals = []
    for name, lhs, kind, rhs in equations:
        delta = evaluate(lhs) - evaluate(rhs)
        residual = abs(delta) if kind == "e" else max(0., delta if kind == "l" else -delta)
        component = symbol_map.bySymbol.get(name, symbol_map.aliases.get(name))
        if component is None:
            component = symbol_map.bySymbol.get(re.sub(r"_(lo|hi)$", "", name))
        residuals.append({"equation": name, "pyomo_component": component.name if component is not None else None,
                          "violation": residual})
    maximum = max(residuals, key=lambda row: row["violation"])
    bound_max, bound_name = max(bound_rows)
    integer_max = max(abs(values[name]-round(values[name])) for name in binary)
    objective_rows = [r for r in residuals if r["pyomo_component"] == model.obj.name]
    require(len(objective_rows) == 1, "Missing GAMS objective-defining equation")
    return {"passes_1e_5": max(maximum["violation"], bound_max, integer_max) <= TOL,
            "equations_checked": len(equations), "variables_checked": len(values),
            "binary_variables_checked": len(binary), "bound_assignments_checked": len(assignments),
            "worst_equation": maximum, "max_bound_violation": bound_max, "worst_bound_symbol": bound_name,
            "worst_bound_component": symbol_map.bySymbol[bound_name].name,
            "max_integrality_violation": integer_max, "objective_equation": objective_rows[0],
            "objective_direction": "minimize", "objective_scale": 1., "objective_offset": 0.,
            "largest_equation_residuals": sorted(residuals, key=lambda row: -row["violation"])[:10]}


def main():
    require(subprocess.run(["git", "merge-base", "--is-ancestor", REVISION, "HEAD"], cwd=ROOT,
                           check=False).returncode == 0, "Checkout does not contain the diagnostic baseline")
    preserved = tracked_hashes()
    require(sha(ARCHIVE.read_bytes()) == four.HASHES["minlp"], "Input archive changed")
    inputs = {str(ARCHIVE.relative_to(ROOT)): sha(ARCHIVE.read_bytes())}
    inputs.update({str(p.relative_to(ROOT)): sha(p.read_bytes())
                   for p in (ROOT / "results/process_scip_four_analysis_20261026").iterdir() if p.is_file()})
    with zipfile.ZipFile(ARCHIVE) as z:
        prefix, _, baseline, metadata = four.verify_return(z, "minlp")
        records = {m: four.read(z, prefix + f"benchmark/dynamic/{m}/result.json") for m in ("bigm", "hull")}
        vectors = {m: four.read(z, prefix + f"benchmark/dynamic/{m}/solution.json") for m in records}
        shared_fields = ("source", "initialization", "dynamic_preparation", "globally_implied_bounds", "template_policy")
        for field in shared_fields:
            require(records["bigm"][field] == records["hull"][field], "Different templates: " + field)
        members = {n: sha(z.read(n)) for n in z.namelist() if
                   n.startswith(prefix + "benchmark/dynamic/") or
                   n.startswith(prefix + "preflight/compile/dynamic/") or
                   n.startswith(prefix + "package/source/gdp_models/")}
        original, execution_original, transformed, exports, aux = {}, {}, {}, {}, {}
        with prior.frozen_models(z, prefix + "package/") as build:
            import pyomo
            import pyomo.environ as pyo
            import pyomo.gdp.plugins.hull as hull_module
            from pyomo.gdp import Disjunct
            from gdp_models.comparison import build_template, reformulate
            # Even direct solver classes cannot launch a child process in this audit.
            with patch("subprocess.Popen", side_effect=AssertionError("No external process allowed in audit")):
                template = build_template("dynamic")
                snapshot = original_snapshot(template.model)
                require(template.metadata["globally_implied_bounds"] == records["hull"]["globally_implied_bounds"],
                        "Reconstructed FBBT bounds differ from execution record")
                for method in records:
                    original[method] = prior.verify_solution(build(records[method]), vectors[method], records[method])
                    execution_original[method] = prior.verify_solution(template.model.clone(), vectors[method], records[method])
                    require(all(v == records[method]["original_validation"].get(k) for k, v in original[method].items()
                                if k not in {"objective_recomputed", "objective_abs_error"}), "Earlier feasibility check differs")
                hull = template.model.clone()
                original_names = {v.name for v in hull.component_data_objects(pyo.Var, descend_into=(pyo.Block, Disjunct))}
                reformulate(hull, "hull")
                with tempfile.TemporaryDirectory(prefix="dynamic-hull-export-") as scratch:
                    bigm = template.model.clone()
                    reformulate(bigm, "bigm")
                    bigm_file, _ = bigm.write(str(Path(scratch) / "bigm.gms"), format="gams",
                                              io_options={"solver": "scip", "mtype": "minlp"})
                    bigm_archived = z.read(prefix + "preflight/compile/dynamic/bigm/model.gms")
                    bigm_generated = Path(bigm_file).read_bytes()
                    exports["bigm"] = {"reconstructed_sha256": sha(bigm_generated), "archived_sha256": sha(bigm_archived),
                                        "byte_identical": bigm_generated == bigm_archived}
                    require(len(bigm_generated.splitlines()) == len(bigm_archived.splitlines()), "Big-M line count differs")
                    bigm_differences = [{"line": i+1, "generated": a, "archived": b}
                                        for i, (a, b) in enumerate(zip(bigm_generated.decode().splitlines(), bigm_archived.decode().splitlines()))
                                        if a != b]
                    exports["bigm"]["different_lines"] = bigm_differences
                    number = r"(?<![\w.])\d+(?:\.\d*)?(?:[Ee][+-]?\d+)?"
                    numeric_deltas = []
                    for difference in bigm_differences:
                        a, b = difference["generated"], difference["archived"]
                        require(re.sub(number, "#", a) == re.sub(number, "#", b), "Big-M algebra differs")
                        numeric_deltas.extend(abs(float(x)-float(y)) for x, y in zip(re.findall(number, a), re.findall(number, b)))
                    exports["bigm"]["maximum_numeric_literal_difference"] = max(numeric_deltas, default=0.)
                    for model in (bigm, hull):
                        after = original_snapshot(model)
                        require(after["objective_expression"] == snapshot["objective_expression"]
                                and after["objective_sense"] == snapshot["objective_sense"], "Changed original objective")
                        require(all(after["variables"][name] == row for name, row in snapshot["variables"].items()),
                                "Transformation changed an original variable bound, domain, fixed flag or initial value")
                    exported, smap_id = hull.write(str(Path(scratch) / "model.gms"), format="gams",
                                                   io_options={"solver": "scip", "mtype": "minlp"})
                    archived = z.read(prefix + "preflight/compile/dynamic/hull/model.gms")
                    generated = Path(exported).read_bytes()
                    exports["hull"] = {"reconstructed_sha256": sha(generated), "archived_sha256": sha(archived),
                                        "byte_identical": generated == archived}
                    require(generated == archived, "Reconstructed Hull export is not identical to the archived preflight")
                    smap = hull.solutions.symbol_map[smap_id]
                    text = archived.decode()
                    require("SOLVE GAMS_MODEL USING minlp minimizing GAMS_OBJECTIVE;" in text, "Changed objective direction")
                    for method in records:
                        rows = lift(hull, original_names, vectors[method])
                        transformed[method] = {"pyomo": algebraic_check(hull), "archived_gams": gams_check(text, hull, smap)}
                        require(transformed[method]["archived_gams"]["equations_checked"] == records["hull"]["gams_statistics"]["NUMEQU"]
                                and transformed[method]["archived_gams"]["variables_checked"] == records["hull"]["gams_statistics"]["NUMVAR"],
                                "Archived export dimensions disagree with actual solve")
                        aux[method] = {"total": len(rows), "branch": sum(r["rule"] == "branch" for r in rows),
                                       "complementary": sum(r["rule"] == "complementary" for r in rows)}
                        if method == "bigm":
                            prior.save_csv(OUT / "bigm_hull_auxiliary_values.csv", rows)
                local = {"python": platform.python_version(), "pyomo": pyomo.__version__,
                         "hull_module_sha256": sha(Path(hull_module.__file__).read_bytes()),
                         "hull_defaults": dict(pyo.TransformationFactory("gdp.hull").CONFIG())}
        logs = {}
        for method in records:
            name = prefix + f"benchmark/dynamic/{method}/run.log"
            lines = z.read(name).decode().splitlines()
            log_text = "\n".join(lines)
            log_primal = float(re.search(r"Primal Bound\s*:\s*(\S+)", log_text).group(1))
            log_dual = float(re.search(r"Dual Bound\s*:\s*(\S+)", log_text).group(1))
            gap = float(re.search(r"Gap\s*:\s*([\d.]+)\s*%", log_text).group(1))
            require(abs(log_dual - records[method]["reported_lower_bound"]) <= 1e-8, "Extracted lower bound differs from log")
            terms = ("SCIP Status", "Primal Bound", "Dual Bound", "Gap ", "Solving Nodes", "Solving Time", "chg bounds",
                     "tightened bounds", "original problem", "presolved problem", "Bound     ", "limits/gap", "lp/threads", "Matrix ")
            logs[method] = {"archive_member": name, "sha256": sha(z.read(name)),
                            "excerpts": [{"line": i+1, "text": line} for i, line in enumerate(lines)
                                         if any(term in line for term in terms) or "| 297.91%" in line or "|   0.00%" in line],
                            "result_fields": {k: records[method][k] for k in ("termination", "solver_status", "gams_statistics",
                                "reported_lower_bound", "reported_upper_bound", "method_wall_s", "scip_options")},
                            "calls": four.journal(z, prefix + f"benchmark/dynamic/{method}/solver_calls.jsonl")}
            logs[method]["parsed_scip"] = {"primal": log_primal, "dual": log_dual, "gap_percent": gap,
                "status": re.search(r"SCIP Status\s*:\s*(.+)", log_text).group(1),
                "primal_minus_recomputed_objective": log_primal - original[method]["objective_recomputed"],
                "dual_minus_extracted_lower_bound": log_dual - records[method]["reported_lower_bound"]}
        diagnostic = {"tolerance": TOL, "new_solver_calls": 0,
            "original_gdp": original, "execution_template_original_gdp": execution_original,
            "hull_lifts": transformed, "auxiliary_counts": aux,
            "hull_lower_bound_minus_bigm_witness": records["hull"]["reported_lower_bound"] - original["bigm"]["objective_recomputed"],
            "same_original_template": {k: records["hull"][k] for k in shared_fields},
            "exports": exports, "local_evaluation_environment": local, "original_solver_logs": logs,
            "model_checks": {"global_fbbt_changed_variables": len(records["hull"]["globally_implied_bounds"]),
                "reproduced_global_fbbt_bounds_exactly": True,
                "same_original_variables_bounds_domains_initial_values_fixed_flags_after_both_transforms": True,
                "same_objective_expression_and_sense_after_both_transforms": True,
                "original_template_snapshot_sha256": sha(json.dumps(snapshot, sort_keys=True).encode()),
                "objective_definition": "Minimize the negative sum of nine discretized integrals of squared states.",
                "explicit_gams_scaling_assignments": re.findall(r"(?im)^.*\.(?:scale|scaleopt)\s*=.*$", text),
                "no_extra_scaling_or_normalization_in_export": True},
            "limits": ["The archived GAMS file is the preflight export, not the deleted solve-time temporary file.",
                       "The complete compiled solver model, presolved problem, cuts and bound-change reasons were not archived.",
                       "The original objective is evaluated at finite-precision returned vectors using the unchanged 1e-5 acceptance tolerance."]}
        save(OUT / "diagnostic.json", diagnostic)
        preserved_after = tracked_hashes()
        require(preserved == preserved_after, "A pre-existing tracked file changed")
        save(OUT / "preserved_files.json", preserved)
        manifest = {"baseline_revision": REVISION,
            "diagnostic_source_revision": "Git commit containing diagnose.py; exact source hash is recorded in output_sha256",
            "remote_branch_checked": "review/cstr15-dantzig-results", "remote_head_at_start": REVISION,
            "scope": "Dynamic Big-M and Hull saved vectors only", "tolerance": TOL,
            "inputs_sha256": inputs, "archive_members_sha256": members,
            "original_execution_source_sha256": baseline["original_source_sha256"],
            "original_package_files_sha256": metadata["execution_source_sha256"],
            "original_execution_environment": metadata["run"]["runtime"], "local_evaluation_environment": local,
            "reconstructed_exports": exports, "original_transform_options": "core.logical_to_linear; gdp.bigm or gdp.hull with no keyword overrides",
            "new_solver_calls": 0, "new_gams_calls": 0,
            "publication_target": {"pull_request": 52, "branch": "review/cstr15-dantzig-results"},
            "ci_requested": False,
            "solver_guards": ["SolverFactory construction blocked by reused frozen_models", "subprocess.Popen blocked during model evaluation"],
            "preservation": {"tracked_files_checked_before_and_after": len(preserved), "all_unchanged": True},
            "reproduce": "PYTHONDONTWRITEBYTECODE=1 /Users/albertlee0125/Repos/RBFopt_Test/.venv-trace-bam5/bin/python results/dynamic_hull_diagnostic_20261026/diagnose.py",
            "output_sha256": {p.name: sha(p.read_bytes()) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "manifest.json"}}
        save(OUT / "manifest.json", manifest)
    print(json.dumps({"new_solver_calls": 0, "original_objectives": {k: v["objective_recomputed"] for k, v in original.items()},
        "hull_lift_passes": {k: {kind: result["passes_1e_5"] for kind, result in v.items()} for k, v in transformed.items()},
        "exports": exports, "auxiliary_counts": aux, "preserved_files": len(preserved)}, indent=2))


if __name__ == "__main__":
    main()
