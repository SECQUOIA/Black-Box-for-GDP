"""Freeze original CSTR30 evaluator, inputs and DFO traces for solver-free timing."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

import measure_cstr30_structural_rejections as protocol

ROOT = Path(__file__).resolve().parent
DFO = "ipopt_dfo_cstr_20261015_174637_r1dzn5tk"
DFO_SHA = "b91afb707229766adcdcfb1ee67406377d1d2ef44839b062ec9e0539893bfefa"
NLP = "dantzig_gdp_gams_20260922_050038_p4q8hy54"
NLP_SHA = "e406b8fae2a90191835eb7332d483c719ebb1675d14d3b0e6d3bf5f7789a197b"


def encoded(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def build(output):
    source_names = ["measure_cstr30_structural_rejections.py", "run_cstr30_structural_dantzig.sh",
                    "docs/cstr30_structural_rejections.txt", "LICENSE"]
    entries = {name: (ROOT / name).read_bytes() for name in source_names}
    inputs = {}
    original_paths = {}
    archives = [(ROOT / "results/archives" / (name + ".zip"), digest) for name, digest in ((DFO, DFO_SHA), (NLP, NLP_SHA))]
    for archive, digest in archives:
        protocol.require(protocol.sha(archive) == digest, "Unexpected source archive: " + str(archive))
    with zipfile.ZipFile(archives[0][0]) as dfo, zipfile.ZipFile(archives[1][0]) as nlp:
        protocol.require(dfo.testzip() is None and nlp.testzip() is None, "Source ZIP CRC failure")
        prefix = DFO + "/reproduction/inputs/cstr_30/"
        for name in dfo.namelist():
            if name.startswith(prefix) and not name.endswith("/"):
                relative = name.removeprefix(prefix)
                inputs["inputs/cstr_30/" + relative] = dfo.read(name)
                original_paths["inputs/cstr_30/" + relative] = f"{archives[0][0].relative_to(ROOT)}!/{name}"
        manifest = json.loads(inputs["inputs/cstr_30/manifest.json"])
        for name in ("evaluations.csv", "manifest.json", "summary.json"):
            protocol.require(inputs[f"inputs/cstr_30/{name}"] == nlp.read(f"{NLP}/gams_ipopt/cstr_30/{name}"), "DFO/NLP original input differs")
        for name in ("__init__.py", "_sources.py", "models.py", "evaluation.py", "solvers.py", "preflight.py"):
            data = nlp.read(f"{NLP}/source/gdp_models/{name}")
            protocol.require(hashlib.sha256(data).hexdigest() == manifest["runtime"]["adapter_sha256"][name], "Historical adapter hash mismatch")
            entries[f"gdp_models/{name}"] = data
        plan = [s for s in json.loads(dfo.read(f"{DFO}/reproduction/plan.json")) if s["cstr_size"] == 30]
        inputs["inputs/dfo/plan.json"] = encoded(plan)
        inputs["inputs/dfo/runs.csv"] = dfo.read(f"{DFO}/runs.csv")
        events = []
        for spec in plan:
            job = spec["job_id"]
            for name in ("spec.json", "result.json", "callbacks.jsonl", "runtime.json", "actual_settings.json"):
                member = f"{DFO}/jobs/{job}/{name}"
                key = f"inputs/dfo/jobs/{job}/{name}"
                inputs[key] = dfo.read(member)
                original_paths[key] = f"{archives[0][0].relative_to(ROOT)}!/{member}"
            events.extend(json.loads(line) for line in inputs[f"inputs/dfo/jobs/{job}/callbacks.jsonl"].decode().splitlines())
        counts = dict(Counter(e["evaluation_state"] for e in events if e["selected_attempt_nlp_s"] is None))
        protocol.require(len(events) == 1615 and counts == {"logical_exclusion_unmeasured": 508, "invalid_callback": 7}, "Unexpected frozen callback gaps")
    for name, digest in manifest["runtime"]["source"]["files_sha256"].items():
        path = ROOT / "external/dsda-gdp" / name
        protocol.require(protocol.sha(path) == digest, "Model evidence changed")
        entries[f"evidence/upstream/{name}.txt"] = path.read_bytes()
    entries.update(inputs)
    entries["coordinates.json"] = encoded(protocol.POINTS)
    entries["README.txt"] = entries["docs/cstr30_structural_rejections.txt"]
    entries["bundle_provenance.json"] = encoded({
        "kind": "cstr30_structural_rejection_timing_only_v1",
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "builder_sha256": protocol.sha(__file__),
        "new_code_sha256": {n: hashlib.sha256(entries[n]).hexdigest() for n in source_names},
        "historical_evaluator_source": f"results/archives/{NLP}.zip!/source/gdp_models/",
        "source_archives_sha256": {str(p.relative_to(ROOT)): d for p, d in archives},
        "input_files_sha256": {n: hashlib.sha256(b).hexdigest() for n, b in inputs.items()},
        "original_member_paths": original_paths,
        "generated_input_notes": {"inputs/dfo/plan.json": "CSTR30-only subset of original immutable DFO plan",
                                  "inputs/dfo/runs.csv": "Original complete 240-run CSV, byte-identical; only40 N30 rows used"},
        "source_policy": "Historical evaluator byte-identical; new measurement/overlay code identified by commit and hashes",
        "structural_points": 435, "original_points": 465, "dfo_callbacks": len(events),
        "expected_structural_callback_fills": 508, "expected_remaining_budget_errors": 7,
        "original_solver_probe_not_repeated": True, "local_production_measurements": 0,
    })
    entries["SHA256SUMS"] = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(entries.items())).encode()
    with tempfile.TemporaryDirectory(prefix="cstr30-structural-build-") as temporary:
        root = Path(temporary)
        for name, data in entries.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        protocol.check_inputs(root)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as target:
        for name, data in entries.items():
            target.writestr("cstr30_structural_runner/" + name, data)
    output.with_suffix(".zip.sha256").write_text(f"{protocol.sha(output)}  {output.name}\n")
    print(f"RUNNER_ZIP={output.resolve()}\nSHA256={protocol.sha(output)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
