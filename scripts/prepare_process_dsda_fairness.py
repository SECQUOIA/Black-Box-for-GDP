"""Freeze current process selection and old DSDA evidence; no optimization runs."""

import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmark_protocols/process_dsda_fairness_reference.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build():
    from scripts.plot_dantzig_cost_breakdown import load_runs, input_hashes
    from scripts.import_fmqa_qhd import publication_points

    panels = [("column", "", 16, "Column"), ("small_batch", "", 10, "Small Batch")]
    panels += [
        ("cstr", str(n), b, f"CSTR {n}")
        for n, b in zip((5, 10, 15, 20, 25, 30), (8, 15, 22, 29, 36, 43))
    ]
    panels += [("dynamic", "", b, "Dynamic") for b in (12, 15, 20, 30, 37, 50)]
    selected, _, prep, inputs, manifest = load_runs(panels)
    assert len(selected) == 560
    old = {r["job_id"]: r for r in selected if r["method"] == "dsda"}
    assert len(old) == 140
    sources = input_hashes(inputs, manifest)
    plans, evidence = [], {}
    archives = [
        (
            "results/archives/dantzig_dfo_trace_nlp_20261002_012137_ttd0c14p.zip",
            "lookup",
            "lookup_plan",
        ),
        (
            json.loads(
                (ROOT / "results/process_followup_20261012/audit.json").read_text()
            )["archive"],
            "jobs",
            "plan",
        ),
        (
            json.loads(
                (
                    ROOT / "results/small_batch_full_domain_20261012/audit.json"
                ).read_text()
            )["archive"],
            "jobs",
            "plan",
        ),
    ]
    for filename, folder, plan_key in archives:
        path = ROOT / filename
        sources[filename] = sha(path.read_bytes())
        with zipfile.ZipFile(path) as z:
            root = next(
                n.removesuffix("run.json")
                for n in z.namelist()
                if n.count("/") == 1 and n.endswith("/run.json")
            )
            checks = dict(
                (rel, digest)
                for digest, rel in (
                    line.split("  ", 1)
                    for line in z.read(root + "SHA256SUMS").decode().splitlines()
                )
            )

            def read(rel):
                data = z.read(root + rel)
                assert sha(data) == checks[rel], rel
                return json.loads(data)

            run = read("run.json")
            for source_name, digest in run["source_files_sha256"].items():
                if source_name.endswith("_dsda.py") or source_name in (
                    "grid_dsda.py",
                    "small_batch_full_domain.py",
                    "instrumentation.py",
                    "evaluation_trace.py",
                ):
                    assert sha(z.read(root + "source/" + source_name)) == digest
            for spec in run[plan_key]:
                if spec["job_id"] not in old or spec["method"] != "dsda":
                    continue
                ident = spec["job_id"]
                if ident in evidence:
                    raise ValueError("Duplicate selected DSDA")
                base = f"{folder}/{ident}/"
                result = read(base + "result.json")
                entries = [
                    json.loads(line)
                    for line in z.read(
                        root + base + result["trace"]["path"]
                    ).splitlines()
                ]
                assert (
                    sha(z.read(root + base + result["trace"]["path"]))
                    == checks[base + result["trace"]["path"]]
                )
                events = [e for e in entries if e.get("event") == "evaluation"]
                assert (
                    result["status"] == "completed"
                    and len(events) == result["result_record"]["total_evals"]
                )
                assert [e["point"] for e in events[:3]] == spec["starting_points"]
                s = dict(spec)
                case = s["case_name"]
                n = s.get("grid_size")
                lo, hi = {
                    "column": ([7, 1], [15, 9]),
                    "cstr": ([1, 1], [n, n]),
                    "dynamic": ([1, 2], [9, 9]),
                    "small_batch": ([1, 1, 1], [3, 3, 3]),
                }[case]
                s.update(
                    lower_bounds=lo,
                    upper_bounds=hi,
                    settings={"diagonal": True, "tie_break": "first"},
                    historical_archive=filename,
                )
                s["target_value"] = old[ident]["target_value"]
                plans.append(s)
                evidence[ident] = {
                    "events": events,
                    "record": result["result_record"],
                    "stop_reason": result.get("stop_reason"),
                    "archive": filename,
                    "archive_member": root + base + "result.json",
                    "source_hashes": {
                        k: v
                        for k, v in run["source_files_sha256"].items()
                        if k.endswith("_dsda.py")
                        or k in ("grid_dsda.py", "small_batch_full_domain.py")
                    },
                }
    assert set(evidence) == set(old)
    qhd = json.loads((ROOT / "results/fmqa_qhd_20261012/run.json").read_text())["plan"]
    canonical = {
        (s["case_name"], s.get("grid_size"), s["max_evaluations"], s["seed"]): s
        for s in qhd
        if s["case_name"] != "grid"
    }
    for s in plans:
        q = canonical[
            s["case_name"], s.get("grid_size"), s["max_evaluations"], s["seed"]
        ]
        assert (
            s["starting_points"] == q["starting_points"]
            and s["initial_design_sha256"] == q["initial_design_sha256"]
        )
        assert (
            sha(json.dumps(s["starting_points"], separators=(",", ":")).encode())
            == s["initial_design_sha256"]
        )
    costs = [
        {"case": k[0], "cstr_size": k[1], "point": list(k[2]), **v}
        for k, v in publication_points().items()
        if k[0] != "grid"
    ]
    # The original publication measurement policy is validated by publication_points:
    # same GAMS/IPOPT/model/initialization, successful CSTR retry, rejection supplement.
    for f in [
        "results/dfo_trace_nlp_20261002/analysis/point_timings.csv",
        "results/fmqa_qhd_20261012/point_supplement.json",
        "benchmark_protocols/small_batch_full_domain.json",
        "overnight_benchmark/reference_archives.json",
    ]:
        sources[f] = sha((ROOT / f).read_bytes())
    value = {
        "kind": "process_dsda_budget_fairness_v1",
        "plan": plans,
        "selected_runs": selected,
        "old_dsda": evidence,
        "point_costs": costs,
        "dynamic_preparation": prep,
        "selection_manifest": manifest,
        "source_files_sha256": sources,
        "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "non_dsda_sha256": sha(
            json.dumps(
                [r for r in selected if r["method"] != "dsda"], sort_keys=True
            ).encode()
        ),
    }
    OUT.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "reference": str(OUT),
                "planned_runs": len(plans),
                "preserved_non_dsda": 420,
                "compatible_costs": len(costs),
                "sha256": sha(OUT.read_bytes()),
            }
        )
    )


if __name__ == "__main__":
    build()
