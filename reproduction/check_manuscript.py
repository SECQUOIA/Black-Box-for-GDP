"""Read external TeX references without copying manuscript sources into the package.

Checks printed numeric cells and classifications against regenerated data.
Explanatory prose, equations and page layout remain editorial checks.
"""

import argparse
from pathlib import Path
import re

from common import METHODS, rows, sha, write_json

NAMES = {
    "dsda": "DSDA",
    "rbfopt": "RBFOpt",
    "bam": "BAM",
    "fmqa_sa": "FMQA-SA",
    "column": "Column",
    "dynamic": "Dynamic",
    "small_batch": "Small Batch",
}


def label(name):
    return NAMES.get(name, name.replace("cstr_", "CSTR "))


def blocks(path):
    return [
        b
        for _, b in re.findall(
            r"\\begin\{(table\*?|longtable)\}(.*?)\\end\{\1\}",
            Path(path).read_text(),
            re.S,
        )
    ]


def line_for(block, prefix):
    return [
        line for line in block.splitlines() if line.strip().startswith(prefix + " &")
    ]


def compare(output, main, supplementary):
    m, s = blocks(main), blocks(supplementary)
    if len(m) != 8 or len(s) != 15:
        raise ValueError("Expected exactly 8 main and 15 supplementary tables")
    checks = []

    def check(name, passed, detail):
        checks.append(dict(check=name, passed=bool(passed), detail=detail))

    def table(name):
        return rows(output / "tables" / f"{name}.csv")

    for r in table("main_01"):
        line = " ".join(line_for(m[0], label(r["case"])))
        check(
            "Table 1 " + r["case"],
            f"& {r['finite_lookup']} & {r['measured_coordinates']} &" in line,
            "accepted and measured coordinate counts",
        )
        digits = 7 if r["case"].startswith("cstr") else 4
        check(
            "Table 1 reference " + r["case"],
            f"{float(r['reference']):.{digits}f}" in line,
            "reference objective, printed precision",
        )
    for r in table("main_03"):
        cells = line_for(m[2], r["budget"])[0].split("&")
        check(
            "Table 3 " + r["budget"] + "/" + r["method"],
            r["display_percent"] in cells[1 + METHODS.index(r["method"])],
            "printed hit percentage",
        )
    for r in table("main_04"):
        line = line_for(m[3], label(r["method"]))[0]
        check(
            "Table 4 " + r["method"],
            all(
                value in line
                for value in [
                    f"{r['hits']}/{r['n']}",
                    f"{float(r['median_completion_s']):.2f}",
                    f"{float(r['median_point_s']):.2f}",
                ]
            ),
            "hits, completion median, point-cost median",
        )
    for r in table("main_06"):
        line = next(
            line_text
            for line_text in line_for(m[5], label(r["case"]))
            if re.match(
                r"\s*"
                + re.escape(label(r["case"]))
                + r"\s*&\s*"
                + r["budget"]
                + r"\s*&",
                line_text,
            )
        )
        cell = line.split("&")[2 + METHODS.index(r["method"])]
        check(
            "Table 6 " + r["case"] + "/" + r["budget"] + "/" + r["method"],
            f"{r['hits']}/{r['n']}" in cell,
            "hits/denominator",
        )
        check(
            "Table 6 failure " + r["case"] + "/" + r["budget"] + "/" + r["method"],
            ("F1" in cell) == (int(r["execution_failures"]) == 1),
            "execution-failure annotation",
        )
    for r in table("main_07"):
        lines = [
            line_text
            for line_text in line_for(m[6], label(r["case"]))
            if re.match(
                r"\s*"
                + re.escape(label(r["case"]))
                + r"\s*&\s*"
                + r["budget"]
                + r"\s*&",
                line_text,
            )
        ]
        for line, field in zip(lines, ["median_completion_s", "tts99_s"]):
            expected = r"\infty" if r[field] == "inf" else f"{float(r[field]):.2f}"
            check(
                "Table 7 "
                + r["case"]
                + "/"
                + r["budget"]
                + "/"
                + r["method"]
                + "/"
                + field,
                expected in line.split("&")[2 + METHODS.index(r["method"])],
                "printed median/TTS99",
            )
    for r in table("main_08"):
        line = line_for(m[7], label(r["instance_id"]))[0]
        cell = line.split("&")[
            1 + ["ric", "gloa", "loa", "bigm", "hull"].index(r["method"])
        ]
        digits = 7 if r["instance_id"].startswith("cstr") else 3
        check(
            "Table 8 " + r["instance_id"] + "/" + r["method"],
            all(
                v in cell
                for v in [
                    f"{float(r['objective']):.{digits}f}",
                    f"{float(r['completion_s']):.2f}",
                ]
            ),
            "objective and preparation-inclusive completion time",
        )
        # A standalone dagger must not be confused with the substring in ddagger.
        check(
            "Table 8 classification " + r["instance_id"] + "/" + r["method"],
            (
                bool(re.search(r"\\dagger(?![a-z])", cell))
                == (r["bound_conflict"] == "True")
            )
            and (r"\ddagger" in cell) == (r["optimal_target_miss"] == "True")
            and (r"\mathrm{TL}" in cell) == (r["termination"] == "maxTimeLimit"),
            "dagger, double dagger, time-limit flags",
        )
    for number in range(8, 14):
        block = s[number - 1]
        # Match the complete four-method hit/interval row, independent of editorial function names.
        grouped = {}
        for r in table(f"supp_{number:02}"):
            grouped.setdefault((r["case"], r["budget"]), {})[r["method"]] = r
        for key, methods in grouped.items():
            cells = [
                f"{methods[method]['hits']} [{float(methods[method]['ci95_lower']):.2f}, {float(methods[method]['ci95_upper']):.2f}]"
                for method in METHODS
            ]
            check(
                f"Table S{number} {key}",
                " & ".join(cells) in block,
                "all four printed exact-binomial intervals",
            )
    for r in table("supp_03"):
        point = (
            "("
            + ",".join(str(v) for v in __import__("json").loads(r["terminal_point"]))
            + ")"
        )
        check(
            "Table S3 " + r["job_id"],
            point in s[2] and r["terminal_accepted_objective"] in s[2],
            "terminal point and full-precision objective",
        )
    for r in table("supp_05"):
        name = "CSTR " + r["size"] if r["case"] == "cstr" else label(r["case"])
        line = line_for(s[4], name)[0]
        values = [
            r[k]
            for k in [
                "continuous_variables",
                "binary_variables",
                "algebraic_constraints",
                "logical_constraints",
                "disjunctions",
            ]
        ]
        check(
            "Table S5 " + name, " & ".join(values) in line, "five original-model counts"
        )
    import json

    # Match function rows by their order in the frozen inventory where historical
    # identifiers differ from the manuscript's expanded display names.
    inventory_rows = table("supp_01")
    printed_grid_lines = [
        line
        for line in m[4].splitlines()
        if " & " in line
        and not any(
            x in line
            for x in ["Problem &", "Target hits", "Executed target", "Unsupported &"]
        )
    ]
    grid_order = [r["function"] for r in inventory_rows]
    domain_lines = [
        line
        for line in s[0].splitlines()
        if " & " in line and not line.startswith("Function &")
    ]
    for r, line in zip(inventory_rows, domain_lines):
        bounds = json.loads(r["bounds"])
        cells = line.split("&")
        expected_bounds = [
            f"[{bounds[i]:g},{bounds[i + 1]:g}]"
            if bounds[i + 1] != 3.141592653589793
            else r"[0,\pi]"
            for i in (0, 2)
        ]
        check(
            "Table S1 " + r["function"],
            all(b in cell for b, cell in zip(expected_bounds, cells[1:3])),
            "two physical coordinate domains",
        )
    for r in table("main_05"):
        cell = printed_grid_lines[grid_order.index(r["grid_name"])].split("&")[
            1 + ["ric", "gloa", "loa", "bigm", "hull"].index(r["method"])
        ]
        check(
            "Table 5 " + r["grid_name"] + "/" + r["method"],
            r["display"] in cell
            and (r"\textsuperscript{T" in cell) == (r["time_limit"] == "True")
            and ("*" in cell) == (r["corrected_profile"] == "True"),
            "time/outcome and execution-profile annotations",
        )
    for r in table("supp_02"):
        line = line_for(s[1], r["family"])[0]
        check(
            "Table S2 " + r["family"],
            all(
                f"{int(r[k]):,}" in line
                for k in ["runs", "proposals", "uniform_fallbacks"]
            )
            and f"{float(r['fallback_percent']):.2f}" in line,
            "proposal/fallback counts and rate",
        )
    for r in table("supp_04"):
        family, method = r["key"].split("/")
        line = next(
            line
            for line in s[3].splitlines()
            if re.match(re.escape(family + " " + label(method)) + r"\s*&", line.strip())
        )
        counts = json.loads(r["stop_counts"])
        cells = [
            str(counts.get(k, 0)) for k in ["budget", "local", "target", "failure"]
        ]
        # Historical spelling for the single execution failure is retained.
        cells[3] = str(counts.get("failure", counts.get("execution_failure", 0)))
        actual = [c.strip() for c in line.split("&")[1:5]]
        check(
            "Table S4 " + r["key"],
            cells == actual
            and f"{int(r['callbacks_total']):,}" in line
            and f"{float(r['post_target_median_successful']):g} ({r['target_hits']})"
            in line,
            "stopping categories, callbacks and post-target median",
        )
    for number in (6, 7):
        lines = [
            line
            for line in s[number - 1].splitlines()
            if " & " in line and not line.startswith("Function &")
        ]
        for r, line in zip(table(f"supp_{number:02}"), lines):
            if number == 6:
                cells = line.split("&")[1:]
                good = all(
                    f"{float(r[k]):.7g}" == cells[i].strip()
                    for i, k in enumerate(["L", "U"])
                )
                good = (
                    good
                    and r["n_min"] == cells[2].strip()
                    and r["n_target"] in cells[3]
                )
            else:
                points = json.loads(r["minimizing_indices"])
                good = all("(" + ",".join(map(str, pt)) + ")" in line for pt in points)
            check(
                f"Table S{number} " + r["name"],
                good,
                "normalization/minimizer inventory",
            )
    for r in table("supp_14"):
        line = line_for(s[13], r["audit_id"])[0]
        lower = r["reported_lower_bound"] or "---"
        ratio = (
            f"{float(r['bound_gap_over_tolerance']):.6g}"
            if r["bound_gap_over_tolerance"]
            else "---"
        )
        check(
            "Table S14 " + r["audit_id"],
            all(
                v in line
                for v in [
                    r["reported_objective"],
                    lower,
                    f"{float(r['original_model_max_violation']):.3e}",
                    r["witness_id"],
                    ratio,
                ]
            )
            and (r"\dagger" in line) == (r["uniform_bound_conflict"] == "True"),
            "objective, lower bound, residual, witness, ratio and flag",
        )
    for r in table("supp_15"):
        line = line_for(s[14], r["witness_id"])[0]
        check(
            "Table S15 " + r["witness_id"],
            all(
                v in line
                for v in [
                    r["recorded_objective"],
                    f"{float(r['max_primal_violation']):.3e}",
                    r["source_alias"],
                ]
            ),
            "witness objective, residual and source",
        )
    report = {
        "reference_files": {
            "main.tex": sha(main),
            "supplementary.tex": sha(supplementary),
        },
        "reference_sources_committed": False,
        "checks": checks,
        "passed": all(r["passed"] for r in checks),
        "failed_checks": [r for r in checks if not r["passed"]],
        "scope": "Automated numeric-cell checks listed individually. Table 2 explanatory prose and table layouts require editorial review. Remaining tables are checked against their frozen evidence by reproduce.py.",
    }
    write_json(output / "manuscript_comparison.json", report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--main", type=Path, required=True)
    p.add_argument("--supplementary", type=Path, required=True)
    a = p.parse_args()
    result = compare(a.output, a.main, a.supplementary)
    print(
        f"{sum(c['passed'] for c in result['checks'])}/{len(result['checks'])} manuscript cell checks passed"
    )
    if not result["passed"]:
        print(result["failed_checks"])
        raise SystemExit(1)
