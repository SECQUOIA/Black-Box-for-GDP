"""Verify saved diagnostic outputs without fits, annealing or NLP calls."""

import argparse
import csv
import math
from pathlib import Path
import zipfile

from .common import ROOT, digest as checksum, read, sha, save


def verify_inputs(directory):
    selection = read(directory / "selection.json")
    if (
        sha(directory / "selection.json")
        != read(directory / "manifest.json")["selection_sha256"]
    ):
        raise ValueError("Frozen selection changed")
    for case in selection["fmqa_cases"]:
        archive = ROOT / case["archive"]
        if sha(archive) != case["archive_sha256"]:
            raise ValueError("Historical archive changed")
        with zipfile.ZipFile(archive) as z:
            for member, digest in case["input_members_sha256"].items():
                raw = z.read(member)
                if checksum(raw) != digest:
                    raise ValueError("Archive member changed")
                name = Path(member).name
                if name in {"run.json", "runtime.json"}:
                    name = "historical_runtime.json"
                local = directory / "inputs" / case["case"] / name
                if name == "rosenbrock.csv":
                    continue  # The domain is recorded in selection; grid objectives are not copied.
                if not local.is_file() or local.read_bytes() != raw:
                    raise ValueError("Local input copy changed")
    return selection


def verify(directory):
    verify_inputs(directory)
    summaries = list(csv.DictReader((directory / "fmqa/summary.csv").open(newline="")))
    identity_rows = 0
    for row in summaries:
        dest = directory / "fmqa" / f"{row['case']}_iteration{row['iteration']}"
        weights = read(dest / "weights.json")
        with (dest / "exhaustive_energy.csv").open(newline="") as stream:
            data = list(csv.DictReader(stream))
        if len(data) != 2 ** int(row["bits"]) or len({r["bits"] for r in data}) != len(
            data
        ):
            raise ValueError("Incomplete exhaustive domain")
        for record in data:
            x = [int(b) for b in record["bits"]]
            raw = weights["bias"] + sum(
                weights["unscaled_Q"][i][j] * x[i] * x[j]
                for i in range(len(x))
                for j in range(len(x))
            )
            scaled = weights["scaled_offset"] + sum(
                float(weights["scaled_linear"][str(i)]) * x[i] for i in range(len(x))
            )
            scaled += sum(q * x[i] * x[j] for i, j, q in weights["scaled_quadratic"])
            if not math.isclose(
                raw,
                float(record["unscaled_qubo_with_bias"]),
                abs_tol=1e-12,
                rel_tol=1e-12,
            ):
                raise ValueError("QUBO energy changed")
            if not math.isclose(
                scaled,
                float(record["bqm_scaled_energy_with_offset"]),
                abs_tol=1e-12,
                rel_tol=1e-12,
            ):
                raise ValueError("BQM energy changed")
            if record["identity_pass"] != "True":
                raise ValueError("Failed identity row")
        identity_rows += len(data)
    fits = read(directory / "fmqa/fit_ledger.json")
    if len(fits) > 9 or not all(r["completed"] for r in fits):
        raise ValueError("Fit cap/completion")
    fm = read(directory / "fmqa/manifest.json")
    for name, digest in fm["outputs_sha256"].items():
        if sha(directory / "fmqa" / name) != digest:
            raise ValueError("Saved FMQA output changed")
    feas = read(directory / "feasibility/manifest.json")
    for name, digest in feas["outputs_sha256"].items():
        if sha(directory / "feasibility" / name) != digest:
            raise ValueError("Saved feasibility output changed")
    if feas["nlp_calls"] > 2:
        raise ValueError("NLP call cap")
    report = {
        "selection_sha256": sha(directory / "selection.json"),
        "fits": len(fits),
        "sa_calls": fm["sa_calls"],
        "binary_strings_verified": identity_rows,
        "nlp_calls": feas["nlp_calls"],
        "feasibility_status": feas["status"],
        "verification_fit_sa_nlp_calls": 0,
        "note": "Saved diagnostic outputs verified; no claim that reconstructed weights equal historical weights.",
    }
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    save(args.output, verify(args.directory.resolve()))
    print(args.output)


if __name__ == "__main__":
    main()
