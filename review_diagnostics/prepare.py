"""Freeze the diagnostic selection before fits, exhaustive energies or polishing."""

import argparse
import ast
import csv
import difflib
import io
from pathlib import Path
import subprocess
import zipfile

from .common import ROOT, digest, save, sha

CASES = (
    (
        "rosenbrock",
        "fmqa_qhd_20261012_034123_8kcczd4b.zip",
        "grid_rosenbrock_B10_seed0_pytorch",
        "source",
        "evaluations.jsonl",
    ),
    (
        "cstr_15",
        "ipopt_dfo_cstr_20261015_174637_r1dzn5tk.zip",
        "cstr_15_B22_seed0_fmqa_sa",
        "reproduction",
        "callbacks.jsonl",
    ),
    (
        "dynamic",
        "ipopt_dfo_non_cstr_20261015_172428_o671edu_.zip",
        "dynamic_B12_seed0_fmqa_sa",
        "reproduction",
        "callbacks.jsonl",
    ),
)


def records(data):
    import json

    return [json.loads(line) for line in data.splitlines() if line.strip()]


def select(proposals):
    chosen = {}
    missing = []
    for source in ("simulated_annealing", "uniform_unseen_fallback"):
        match = next((p for p in proposals if p["source"] == source), None)
        if match is None:
            missing.append(source)
        else:
            chosen.setdefault(match["iteration"], []).append("first_" + source)
    chosen.setdefault(proposals[-1]["iteration"], []).append("last_proposal")
    return chosen, missing


def prepare(output):
    import json

    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "inputs"
    items, sources = [], []
    for case, archive_name, job, source, events_name in CASES:
        path = ROOT / "results/archives" / archive_name
        with zipfile.ZipFile(path) as z:
            root = z.namelist()[0].split("/")[0]
            base = f"{root}/jobs/{job}/"
            spec = json.loads(z.read(base + "spec.json"))
            proposals = records(z.read(base + "proposals.jsonl"))
            selected, missing = select(proposals)
            members = [
                n for n in z.namelist() if n.startswith(base) and not n.endswith("/")
            ]
            # Inventory every job member before deciding whether a snapshot exists.
            snapshots = [
                n
                for n in members
                if any(s in n.lower() for s in ("weight", "qubo", "bqm", ".pt", ".npz"))
            ]
            if snapshots:
                raise ValueError(
                    f"Inspect saved snapshots before reconstructing: {snapshots}"
                )
            event_bytes = z.read(base + events_name)
            evaluations = records(event_bytes)
            if case == "rosenbrock":
                evaluations = [e for e in evaluations if e.get("event") == "evaluation"]
            local = inputs / case
            local.mkdir(parents=True)
            member_hashes = {}
            for name in ("spec.json", "proposals.jsonl", events_name, "result.json"):
                raw = z.read(base + name)
                (local / name).write_bytes(raw)
                member_hashes[base + name] = digest(raw)
            source_prefix = f"{root}/{source}/"
            source_hashes = {}
            for member in z.namelist():
                if not member.startswith(
                    source_prefix + "fmqa_benchmark/"
                ) or member.endswith("/"):
                    continue
                relative = member.removeprefix(source_prefix)
                if not (
                    relative.endswith(".py")
                    or relative.startswith("fmqa_benchmark/vendor/")
                ):
                    continue
                raw = z.read(member)
                source_hashes[relative] = digest(raw)
                if (ROOT / relative).is_file():
                    current = (ROOT / relative).read_bytes()
                    sources.append(
                        {
                            "case": case,
                            "archive": str(path.relative_to(ROOT)),
                            "member": member,
                            "path": relative,
                            "historical_sha256": digest(raw),
                            "current_sha256": digest(current),
                            "identical": raw == current,
                        }
                    )
                    if raw != current:
                        diff = "".join(
                            difflib.unified_diff(
                                raw.decode().splitlines(True),
                                current.decode().splitlines(True),
                                fromfile=member,
                                tofile=relative,
                            )
                        )
                        dest = (
                            output
                            / "source_diffs"
                            / case
                            / (relative.replace("/", "__") + ".diff")
                        )
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_text(diff)
            runtime = base + "runtime.json"
            if runtime not in z.namelist():
                runtime = f"{root}/run.json"
            (local / "historical_runtime.json").write_bytes(z.read(runtime))
            member_hashes[runtime] = digest(z.read(runtime))
            lower = spec.get("lower", [1, 1])
            upper = spec.get("upper", [31, 31])
            if case == "rosenbrock":
                # Bounds are recorded by the historical lookup problem, checked against its grid.
                grid_member = source_prefix + "benchmark_grids/rosenbrock.csv"
                grid = list(csv.DictReader(io.StringIO(z.read(grid_member).decode())))
                points = [ast.literal_eval(r["Point"]) for r in grid]
                lower = [min(p[k] for p in points) for k in (0, 1)]
                upper = [max(p[k] for p in points) for k in (0, 1)]
                member_hashes[grid_member] = digest(z.read(grid_member))
            iterations = []
            for p in proposals:
                if p["iteration"] not in selected:
                    continue
                prefix = evaluations[: p["training_points"]]
                if len(prefix) != p["training_points"] or len(prefix) != len(
                    p["training_targets"]
                ):
                    raise ValueError("Training prefix length mismatch")
                iterations.append(
                    {
                        "iteration": p["iteration"],
                        "reasons": selected[p["iteration"]],
                        "training_points": p["training_points"],
                        "fm_seed": p["fm_seed"],
                        "sa_seed": p["sa_seed"],
                        "proposal_source": p["source"],
                        "bit_count": sum(int(h).bit_length() for h in upper),
                    }
                )
            items.append(
                {
                    "case": case,
                    "job_id": job,
                    "archive": str(path.relative_to(ROOT)),
                    "archive_sha256": sha(path),
                    "source_prefix": source_prefix,
                    "source_files_sha256": source_hashes,
                    "input_members_sha256": member_hashes,
                    "job_members": members,
                    "saved_model_snapshots": snapshots,
                    "lower": lower,
                    "upper": upper,
                    "settings": spec["settings"],
                    "events_name": events_name,
                    "iterations": iterations,
                    "missing_proposal_types": missing,
                }
            )
    if sum(len(i["iterations"]) for i in items) > 9:
        raise ValueError("More than nine diagnostic fits")
    audit = ROOT / "reproduction/data/algebraic_audit"
    for line in (audit / "SHA256SUMS").read_text().splitlines():
        h, name = line.split(None, 1)
        if sha(audit / name.lstrip("* ")) != h:
            raise ValueError(f"Algebraic input checksum differs: {name}")

    def rows(name):
        with (audit / name).open(newline="") as stream:
            return list(csv.DictReader(stream))

    a12 = next(r for r in rows("table8_bound_audit.csv") if r["audit_id"] == "A12")
    w03 = next(r for r in rows("feasible_witnesses.csv") if r["witness_id"] == "W03")
    save(
        output / "selection.json",
        {
            "baseline_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "selection_rule": "Fixed Rosenbrock B10 seed0, CSTR15 B22 seed0, Dynamic B12 seed0; first SA-selected, first uniform-fallback and last proposal; deduplicate; never replace missing types.",
            "interpretation": "Purposive diagnostics, not a sample for population frequency estimation.",
            "maximum_fits": 9,
            "fmqa_external_wall_limit_s": 1200,
            "maximum_nlp_calls": 2,
            "nlp_external_wall_limit_per_call_s": 300,
            "fmqa_cases": items,
            "source_comparison": sources,
            "current_adapter": {
                "path": "fmqa_benchmark/adapter.py",
                "sha256": sha(ROOT / "fmqa_benchmark/adapter.py"),
                "historically_present": False,
            },
            "feasibility": {
                "audit": a12,
                "witness": w03,
                "targets": [1e-8, 1e-10],
                "inputs_sha256": {
                    str(p.relative_to(ROOT)): sha(p)
                    for p in audit.rglob("*")
                    if p.is_file()
                },
            },
        },
    )
    save(
        output / "manifest.json",
        {
            "phase": "selection frozen before diagnostic computation",
            "selection_sha256": sha(output / "selection.json"),
        },
    )
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    print(prepare(p.parse_args().output.resolve()))


if __name__ == "__main__":
    main()
