"""Recover only uniquely determined historical RBFOpt grid callback coordinates.

No optimizer is rerun. Ambiguous coordinates remain candidate sets. The log's
rounded elapsed times are preserved as log times, never as precise callbacks.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "results/archives/dantzig_20260910_170759_slN8tv.zip"
PREFIX = "dantzig_20260910_170759_slN8tv/"
ARCHIVE_SHA256 = "c5b706aa20f5577446d84f829910b5825221a9f6c5713ffc1fd854e7315d6e98"
REFERENCE = ROOT / "fmqa_benchmark/reference/grid"
ATOL = 1e-12
HEADER = "  Iter  Cycle  Action             Objective value      Time      Gap"
# Parse individual lines: \s must never consume the next row after Discarded.
ROW = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\w+)\s+([-+\d.eE]+)(~?)\s+"
    r"([-+\d.eE]+)\s+([-+\d.eE]+)\s*(\*?)\s*$"
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def read_inputs(archive=ARCHIVE):
    raw = archive.read_bytes()
    if digest(raw) != ARCHIVE_SHA256:
        raise ValueError("Historical archive hash mismatch")
    meta = json.loads((REFERENCE / "reference.json").read_text())
    for name, expected in meta["files_sha256"].items():
        if digest((REFERENCE / name).read_bytes()) != expected:
            raise ValueError(f"Reference hash mismatch: {name}")
    for name, expected in meta["data_files_sha256"].items():
        if digest((ROOT / name).read_bytes()) != expected:
            raise ValueError(f"Grid hash mismatch: {name}")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive_file:
        raw_csv = archive_file.read(PREFIX + "benchmark.csv")
        raw_log = archive_file.read(PREFIX + "run.log")
        packages = archive_file.read(PREFIX + "python-packages.txt").decode()
    if raw_csv != (REFERENCE / "original.csv").read_bytes():
        raise ValueError("Frozen reference is not the original benchmark CSV")
    if "rbfopt==4.3.0" not in packages.lower():
        raise ValueError("Unexpected original RBFOpt version")
    records = [
        r
        for r in csv.DictReader(io.StringIO(raw_csv.decode()))
        if r["method"] == "RBFOpt"
    ]
    audit = json.loads((REFERENCE / "comparison_audit.json").read_text())
    designs = {
        (d["csv_name"], d["seed"]): [tuple(p) for p in d["starting_points"]]
        for d in audit["grid_designs"]
    }
    grids = {}
    for name in sorted({r["csv_name"] for r in records}):
        with (ROOT / "benchmark_grids" / name).open() as stream:
            grids[name] = {
                (int(r["x"]), int(r["y"])): float(r["z_norm"])
                for r in csv.DictReader(stream)
            }
        if len(grids[name]) != 961:
            raise ValueError(f"Incomplete grid: {name}")
    blocks = parse_log(raw_log.decode())
    keys = {(r["csv_name"], int(r["seed"]), int(r["max_evals"])) for r in records}
    expected = {
        (g, s, b) for g in grids for s in range(10) for b in (10, 30, 50, 70, 100)
    }
    if len(records) != 1050 or len(blocks) != 1050 or keys != expected:
        raise ValueError("Incomplete or duplicate 1,050-case grid matrix")
    sources = {
        "archive": str(ARCHIVE.relative_to(ROOT)),
        "archive_sha256": digest(raw),
        "csv_member": PREFIX + "benchmark.csv",
        "csv_sha256": digest(raw_csv),
        "log_member": PREFIX + "run.log",
        "log_sha256": digest(raw_log),
        "initial_design_file": str(
            (REFERENCE / "comparison_audit.json").relative_to(ROOT)
        ),
        "initial_design_sha256": digest(
            (REFERENCE / "comparison_audit.json").read_bytes()
        ),
        "grid_sha256": meta["data_files_sha256"],
        "recovery_script_sha256": digest(Path(__file__).read_bytes()),
    }
    return records, blocks, designs, grids, sources


def parse_log(text):
    blocks, current = [], None
    for number, line in enumerate(text.splitlines(), 1):
        if "[2/4] All process cases:" in line:
            break
        if line == HEADER:
            if current is not None:
                raise ValueError("Missing RBFOpt summary before next header")
            current = {"header_line": number, "events": [], "restart_lines": []}
        elif current is not None and line.startswith("Summary:"):
            match = re.search(r"evals\s+(\d+).*?obj\s+([-+\d.eE]+)", line)
            if not match:
                raise ValueError("Unrecognized RBFOpt summary")
            current.update(
                summary_line=number,
                summary_evals=int(match[1]),
                summary_value=float(match[2]),
            )
            blocks.append(current)
            current = None
        elif current is not None:
            if "Restart" in line:
                current["restart_lines"].append(number)
            match = ROW.fullmatch(line)
            if match:
                if match[5]:
                    raise ValueError("Noisy objective values are not supported")
                current["events"].append(
                    {
                        "log_line": number,
                        "iteration": int(match[1]),
                        "cycle": int(match[2]),
                        "action": match[3],
                        "printed_objective": match[4],
                        "log_elapsed_s": float(match[6]),
                    }
                )
    if current is not None:
        raise ValueError("Truncated RBFOpt log")
    return blocks


def augment(domains, assignment, owner, left, seen, forbidden=None):
    for point in sorted(domains[left]):
        if (left, point) == forbidden or point in seen:
            continue
        seen.add(point)
        previous = owner.get(point)
        if previous is not None and not augment(
            domains, assignment, owner, previous, seen, forbidden
        ):
            continue
        assignment[left] = point
        owner[point] = left
        return True
    return False


def matching(domains, required_point=None):
    """Find an injective assignment, optionally containing the final best point."""
    assignment, owner = {}, {}
    for left in sorted(range(len(domains)), key=lambda i: (len(domains[i]), i)):
        if not augment(domains, assignment, owner, left, set()):
            raise ValueError("No trajectory satisfies recorded unique-evaluation count")
    if required_point is not None and required_point not in owner:
        options = [i for i, domain in enumerate(domains) if required_point in domain]
        if not options:
            raise ValueError(
                "Final best point is absent from all evaluation candidates"
            )
        # The required point is unused, so replacing any incident edge is valid.
        assignment[options[0]] = required_point
    return [assignment[i] for i in range(len(domains))]


def alternative(domains, baseline, index, required_point=None):
    """Find an alternate assignment for one row, or prove its point is forced.

    Changing a matched edge requires an alternating path/cycle. If that edge
    held the mandatory best point, two separate paths may be needed: solve
    the reduced matching problem instead of restricting one augmenting path.
    """
    old = baseline[index]
    if old == required_point:
        reduced = [set(domain) for domain in domains]
        reduced[index].discard(old)
        try:
            return matching(reduced, required_point)
        except ValueError:
            return None
    assignment = {i: point for i, point in enumerate(baseline) if i != index}
    owner = {point: i for i, point in assignment.items()}
    if augment(
        domains,
        assignment,
        owner,
        index,
        set(),
        forbidden=(index, old),
    ):
        return [assignment[i] for i in range(len(domains))]
    return None


def validate_assignment(points, record, grid, initial, *, complete):
    n = len(points)
    if points[:3] != initial or len(set(points)) != n:
        raise ValueError("Recovered initial design/unique count failed validation")
    history = json.loads(record["incumbent_trajectory"])
    best, errors = math.inf, []
    for point, expected in zip(points, history):
        best = min(best, grid[point])
        errors.append(abs(best - expected))
    if n > len(history) or max(errors, default=0) > ATOL:
        raise ValueError("Recovered points do not reproduce incumbent history")
    if complete:
        expected_best = tuple(json.loads(record["best_point"]))
        if (
            n != int(record["total_evals"])
            or n != int(record["unique_evals"])
            or expected_best not in points
            or abs(grid[expected_best] - best) > ATOL
            or abs(best - float(record["best_value"])) > ATOL
        ):
            raise ValueError("Recovered full trajectory failed final-result checks")
    return max(errors, default=0)


def recover_case(record, block, initial, grid):
    total = int(record["total_evals"])
    history = json.loads(record["incumbent_trajectory"])
    if total != int(record["unique_evals"]) or len(history) != total:
        raise ValueError(
            "This recovery requires the archived all-unique callback protocol"
        )
    if (
        block["summary_evals"] != int(record["solver_evalcount"])
        or abs(block["summary_value"] - float(record["best_value"])) > 0.5e-6 + ATOL
    ):
        raise ValueError("Log/CSV run ordering or summary mismatch")
    first_restart = min(block["restart_lines"], default=math.inf)
    aligned = [e for e in block["events"] if e["log_line"] < first_restart]
    full_alignment = not block["restart_lines"] and len(aligned) == total
    if not full_alignment and not block["restart_lines"]:
        raise ValueError("Unexplained log/callback count mismatch")
    if len(aligned) > total or any(
        e["action"] != "Initialization" for e in aligned[:3]
    ):
        raise ValueError("Invalid initial callback alignment")
    domains = []
    previous = math.inf
    # Accurate-mode RBFOpt 4.3 retains the first strict global minimum:
    # restart initializes with argmin; add_node updates fbest only on '<'.
    final_best_index = max(
        i for i, value in enumerate(history) if i == 0 or value < history[i - 1]
    )
    final_best_point = tuple(json.loads(record["best_point"]))
    for i, event in enumerate(aligned):
        printed, incumbent = float(event["printed_objective"]), history[i]
        candidates = {
            point
            for point, value in grid.items()
            if abs(value - printed) <= 0.5e-6 + ATOL
            and (
                abs(value - incumbent) <= ATOL
                if incumbent < previous
                else value >= incumbent - ATOL
            )
        }
        if i < 3:
            candidates &= {initial[i]}
        if i == final_best_index:
            candidates &= {final_best_point}
        if not candidates:
            raise ValueError(f"No consistent coordinates at evaluation {i + 1}")
        domains.append(candidates)
        previous = incumbent
    required = tuple(json.loads(record["best_point"])) if full_alignment else None
    baseline = matching(domains, required)
    validate_assignment(baseline, record, grid, initial, complete=full_alignment)
    forced, witness = {}, None
    for i, domain in enumerate(domains):
        other = alternative(domains, baseline, i, required) if len(domain) > 1 else None
        if other is None:
            forced[i] = baseline[i]
        elif witness is None:
            validate_assignment(other, record, grid, initial, complete=full_alignment)
            witness = {
                "changed_evaluation_index": i + 1,
                "assignment_a": baseline,
                "assignment_b": other,
                "scope": "complete callbacks"
                if full_alignment
                else "pre-restart callbacks",
                "note": "Witnesses of ambiguity under saved observations; not claimed historical paths",
            }
    complete = full_alignment and len(forced) == total
    status = (
        "recovered"
        if complete
        else "partial_ambiguous"
        if full_alignment
        else "partial_restart_alignment"
    )
    reason = (
        "all callback coordinates uniquely determined and independently validated"
        if complete
        else "rounded objective values and saved constraints admit multiple coordinate sequences"
        if full_alignment
        else "post-restart log mixes cached nodes with new evaluations; callback alignment unproven"
    )
    return {
        "case_id": f"grid_{Path(record['csv_name']).stem}_B{record['max_evals']}_seed{record['seed']}_rbfopt",
        "grid_name": Path(record["csv_name"]).stem,
        "seed": int(record["seed"]),
        "budget": int(record["max_evals"]),
        "status": status,
        "reason": reason,
        "total_evaluations": total,
        "logged_value_rows": len(block["events"]),
        "aligned_evaluations": len(aligned),
        "recovered_evaluations": len(forced),
        "ambiguous_evaluations": len(aligned) - len(forced),
        "unaligned_evaluations": total - len(aligned),
        "historical_wall_time_s": float(record["wall_time_s"]),
        "final_best_point": list(json.loads(record["best_point"])),
        "final_best_evaluation_index": final_best_index + 1,
        "final_best_value": float(record["best_value"]),
        "max_incumbent_abs_error": validate_assignment(
            baseline, record, grid, initial, complete=full_alignment
        ),
        "log_header_line": block["header_line"],
        "log_summary_line": block["summary_line"],
        "restart_lines": block["restart_lines"],
        "events": aligned,
        "unaligned_log_events": block["events"][len(aligned) :],
        "domains": domains,
        "forced": forced,
        "ambiguity_witness": witness,
    }


def write_csv(path, rows, fields):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: encode(v) if isinstance(v, (dict, list)) else v
                    for k, v in row.items()
                    if k in fields
                }
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "results/rbfopt_trajectory_20261008"
    )
    args = parser.parse_args()
    records, blocks, designs, grids, sources = read_inputs()
    cases = []
    for record, block in zip(records, blocks):
        cases.append(
            recover_case(
                record,
                block,
                designs[record["csv_name"], int(record["seed"])],
                grids[record["csv_name"]],
            )
        )
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    fields = [
        k
        for k in cases[0]
        if k
        not in {
            "events",
            "unaligned_log_events",
            "domains",
            "forced",
            "ambiguity_witness",
        }
    ]
    write_csv(output / "cases.csv", cases, fields)
    write_csv(
        output / "recovered_cases.csv",
        [c for c in cases if c["status"] == "recovered"],
        fields,
    )
    write_csv(
        output / "unresolved_cases.csv",
        [c for c in cases if c["status"] != "recovered"],
        fields,
    )
    coordinates, trajectories, unresolved = [], [], []
    for case in cases:
        events = []
        for i, event in enumerate(case["events"]):
            common = {
                "case_id": case["case_id"],
                "grid_name": case["grid_name"],
                "seed": case["seed"],
                "budget": case["budget"],
                "evaluation_index": i + 1,
                **event,
            }
            if i in case["forced"]:
                point = case["forced"][i]
                row = {
                    **common,
                    "x": point[0],
                    "y": point[1],
                    "objective": grids[case["grid_name"] + ".csv"][point],
                    "case_status": case["status"],
                    "evidence": "frozen_initial_design"
                    if i < 3
                    else "unique_under_saved_constraints",
                }
                coordinates.append(row)
                events.append(row)
            else:
                unresolved.append(
                    {
                        **common,
                        "candidate_points": sorted(case["domains"][i]),
                        "note": "Conservative candidates; some may be excluded by global matching constraints",
                    }
                )
        if case["status"] == "recovered":
            trajectories.append({"case_id": case["case_id"], "events": events})
        if case["unaligned_log_events"]:
            unresolved.append(
                {
                    "case_id": case["case_id"],
                    "reason": case["reason"],
                    "unaligned_log_events": case["unaligned_log_events"],
                }
            )
    write_csv(output / "recovered_coordinates.csv", coordinates, list(coordinates[0]))
    (output / "recovered_trajectories.jsonl").write_text(
        "".join(encode(r) + "\n" for r in trajectories)
    )
    for filename, rows in (
        ("unresolved_candidates.jsonl.gz", unresolved),
        (
            "ambiguity_witnesses.jsonl.gz",
            [
                {"case_id": c["case_id"], **c["ambiguity_witness"]}
                for c in cases
                if c["ambiguity_witness"]
            ],
        ),
    ):
        with (output / filename).open("wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream:
                for row in rows:
                    stream.write((encode(row) + "\n").encode())
    by_grid = []
    for name in grids:
        subset = [c for c in cases if c["grid_name"] == Path(name).stem]
        recovered = [c for c in subset if c["status"] == "recovered"]
        by_grid.append(
            {
                "grid_name": Path(name).stem,
                "cases": len(subset),
                "recovered_cases": len(recovered),
                "unresolved_cases": len(subset) - len(recovered),
                "recovered_evaluations": sum(
                    c["recovered_evaluations"] for c in subset
                ),
                "historical_time_of_recovered_cases_h": sum(
                    c["historical_wall_time_s"] for c in recovered
                )
                / 3600,
            }
        )
    write_csv(output / "grid_summary.csv", by_grid, list(by_grid[0]))
    report = {
        "cases": len(cases),
        "recovered_cases": len(trajectories),
        "unresolved_cases": len(cases) - len(trajectories),
        "recovered_callback_coordinates": len(coordinates),
        "coordinates_in_complete_trajectories": sum(
            len(t["events"]) for t in trajectories
        ),
        "total_original_callbacks": sum(c["total_evaluations"] for c in cases),
        "restart_alignment_cases": sum(
            c["status"] == "partial_restart_alignment" for c in cases
        ),
        "historical_time_of_recovered_cases_h": sum(
            c["historical_wall_time_s"] for c in cases if c["status"] == "recovered"
        )
        / 3600,
        "historical_time_of_unresolved_cases_h": sum(
            c["historical_wall_time_s"] for c in cases if c["status"] != "recovered"
        )
        / 3600,
        "objective_atol": ATOL,
        "printed_objective_half_step": 0.5e-6,
        "log_time_resolution_s": 0.01,
        "method": "rounded objective + original full-precision incumbent history + frozen initial coordinates + all-unique evaluations + RBFOpt 4.3 first-strict-best coordinate; alternating-path uniqueness proof",
        "scope": "Uniqueness under retained observations. No optimizer replay or guessed coordinates. Restart runs keep the verified pre-restart prefix only.",
        "time_scope": "Rounded optimizer log times, not newly measured or precise callback timestamps",
        "by_grid": by_grid,
        "sources": sources,
    }
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "recovery_report.txt").write_text(
        "Historical RBFOpt grid trajectory recovery\n\n"
        + f"Complete trajectories recovered: {len(trajectories)} / {len(cases)}\n"
        + f"Individually proven callback coordinates: {len(coordinates)} / 54600\n\n"
        + "Full recoveries by grid (out of 50 cases each):\n"
        + "".join(
            f"  {r['grid_name']}: {r['recovered_cases']} recovered, {r['unresolved_cases']} unresolved\n"
            for r in by_grid
        )
        + "\nFully recovered case IDs:\n"
        + "".join(f"  {c['case_id']}\n" for c in cases if c["status"] == "recovered")
        + "\n"
        + "recovered_cases.csv: complete usable historical trajectories.\n"
        + "unresolved_cases.csv: cases whose entire callback path cannot be established from retained observations.\n"
        + "recovered_coordinates.csv: all individually proven coordinates, including partial cases; evaluation_index is 1-based, x/y are grid indices 0..30.\n"
        + "recovered_trajectories.jsonl: complete cases only, in original evaluation order.\n"
        + "unresolved_candidates.jsonl.gz: unresolved candidate coordinates or post-restart log rows.\n"
        + "ambiguity_witnesses.jsonl.gz: alternative sequences compatible with retained observations, NOT recovered historical coordinates.\n\n"
        + "Log elapsed times are rounded to 0.01 seconds and have a different origin from newly instrumented callback clocks. Do not treat them as precise callback timings.\n"
        + "Inference uses the accurate, serial RBFOpt 4.3 behavior: the first strict global minimum gives the returned best point, and pre-restart value rows correspond to objective calls. Final best-point indices are saved explicitly.\n"
        + "The saved unique-evaluation counts are equal to total evaluations in every original run; this justifies the injective matching constraint. Initial three points come from the frozen design audit.\n"
        + "Each claimed coordinate is forced under these retained constraints. A candidate set or ambiguity witness must not be used as an observed trajectory.\n"
        + "A partial case is not declared impossible to recover by any future method; additional evidence or replay might resolve it.\n\n"
        + "Reproduce: python recover_grid_rbfopt_trajectory.py\n"
    )
    shutil_source = output / "recovery_source.py"
    shutil_source.write_bytes(Path(__file__).read_bytes())
    files = sorted(
        p for p in output.iterdir() if p.is_file() and p.name != "SHA256SUMS"
    )
    (output / "SHA256SUMS").write_text(
        "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in files)
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"sources", "by_grid"}},
            indent=2,
        )
    )
    for row in by_grid:
        print(encode(row))


if __name__ == "__main__":
    main()
