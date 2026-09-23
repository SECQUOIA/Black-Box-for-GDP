"""Pair audited FMQA-SA runs with original DSDA/RBFOpt and BAM 5.0.0."""

import argparse
from contextlib import contextmanager
import csv
import json
import math
from pathlib import Path
import stat
import tempfile
import zipfile

from fmqa_benchmark.protocol import METHOD, REFERENCE, key, reference_plan, sha, verify_lookup_sources
from fmqa_benchmark_runner import KIND, environment, result_record, save, validate_job


@contextmanager
def result_directory(path):
    path = Path(path).resolve()
    if path.suffix.lower() != ".zip":
        yield path.parent if path.is_file() else path
        return
    with tempfile.TemporaryDirectory(prefix="fmqa_compare_") as temp:
        root = Path(temp).resolve()
        with zipfile.ZipFile(path) as archive:
            names = set()
            for member in archive.infolist():
                target = (root / member.filename).resolve()
                if (not target.is_relative_to(root) or member.filename in names
                        or stat.S_ISLNK(member.external_attr >> 16)):
                    raise ValueError("Unsafe or duplicate result ZIP member")
                names.add(member.filename)
            archive.extractall(root)
        candidates = list(root.glob("*/run.json"))
        if len(candidates) != 1:
            raise ValueError("Expected one FMQA run directory in the ZIP")
        yield candidates[0].parent


def rows(path):
    with Path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def verify_artifacts(directory, hashes):
    for relative, expected in hashes.items():
        path = directory / relative
        if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink():
            raise ValueError("Unsafe artifact path")
        if sha(path) != expected:
            raise ValueError(f"FMQA artifact checksum mismatch: {relative}")


def audit_fmqa(directory):
    from case_study_analysis import load_case_study_results
    from instrumentation import RESULT_FIELDS
    directory = Path(directory)
    csv_path = directory / "process_case_studies.csv"
    manifest = json.loads(csv_path.with_suffix(".manifest.json").read_text())
    run = json.loads((directory / "run.json").read_text())
    if run["kind"] != KIND or manifest["fmqa_protocol"] != run:
        raise ValueError("FMQA run and CSV manifests do not match")
    if run["runtime"]["lookup_data_sha256"] != verify_lookup_sources():
        raise ValueError("FMQA and baseline lookup tables differ")
    frozen = {key(s): s for s in reference_plan()}
    plan = run["plan"]
    if not plan or len({key(s) for s in plan}) != len(plan):
        raise ValueError("Empty or duplicate FMQA run plan")
    for spec in plan:
        if frozen.get(key(spec)) != spec:
            raise ValueError("FMQA condition or initial points differ from the original protocol")
    artifacts = manifest["artifacts_sha256"]
    actual = {p.relative_to(directory).as_posix() for p in (directory / "jobs").rglob("*") if p.is_file()}
    if set(artifacts) != actual:
        raise ValueError("Incomplete FMQA artifact checksum inventory")
    verify_artifacts(directory, artifacts)
    verify_artifacts(directory / "source", run["source_sha256"])
    frame = load_case_study_results(csv_path)
    if len(frame) != len(plan) or set(frame["method"]) != {METHOD}:
        raise ValueError("FMQA CSV does not match the planned run count or method")
    by_key = {key(row): row for row in frame.to_dict("records")}
    for spec in plan:
        result = validate_job(directory / "jobs" / spec["job_id"], spec)
        expected = result_record(spec, result)
        if any(by_key.get(key(spec), {}).get(field) != expected[field] for field in RESULT_FIELDS
               if field not in {"best_value", "wall_time_s"}):
            raise ValueError("FMQA CSV differs from the objective trace or terminal outcome")
        # pandas' decimal parser may round the last digit of a CSV float.
        for field in ("best_value", "wall_time_s"):
            if not math.isclose(by_key[key(spec)][field], expected[field], rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("FMQA CSV differs from the recorded objective or completion time")
    return run


def combine(directory, output_dir):
    from case_study_analysis import EXPECTED_RESULT_SCHEMA, load_case_study_results
    from instrumentation import RESULT_FIELDS
    run = audit_fmqa(directory)
    if json.loads((REFERENCE / "bam5-version.json").read_text())["package"] != "5.0.0":
        raise ValueError("Comparison requires BAM 5.0.0")
    chosen = {key(s) for s in run["plan"]}
    combined, inputs = [], {}
    for name, allowed in (("original", {"DSDA", "RBFOpt"}), ("bam5", {"BAM"})):
        path = REFERENCE / f"{name}.csv"
        load_case_study_results(path)
        manifest = json.loads(path.with_suffix(".manifest.json").read_text())
        lookup = dict(manifest["provenance"]["data_files_sha256"])
        lookup["case_studies/dynamic_case.py"] = manifest["provenance"]["source_files_sha256"]["case_studies/dynamic_case.py"]
        if lookup != run["runtime"]["lookup_data_sha256"]:
            raise ValueError(f"{name} objective tables differ from FMQA")
        designs = {(d["case_name"], d.get("grid_size"), d["seed"]): d
                   for d in manifest["provenance"]["initial_design"]["designs"]}
        for spec in run["plan"]:
            design = designs[(spec["case_name"], spec["grid_size"], spec["seed"])]
            if design["sha256"] != spec["initial_design_sha256"] or design["n_starts"] != spec["n_starts"]:
                raise ValueError(f"{name} initial designs differ from FMQA")
        selected = [r for r in rows(path) if r["method"] in allowed and key(r) in chosen]
        for method in allowed:
            if {key(r) for r in selected if r["method"] == method} != chosen:
                raise ValueError(f"Missing paired baseline runs: {method}")
        for row in selected:
            if row["method"] == "BAM":
                row["method"] = "BAM 5.0.0"
        combined.extend(selected)
        inputs[name] = {"csv_sha256": sha(path), "manifest_sha256": sha(path.with_suffix(".manifest.json")),
                        "software": manifest.get("software")}
    fmqa_csv = Path(directory) / "process_case_studies.csv"
    combined.extend(rows(fmqa_csv))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "process_case_studies.csv"
    if output.resolve() == fmqa_csv.resolve():
        raise ValueError("Comparison output must differ from the original FMQA result directory")
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(combined)
    save(output.with_suffix(".manifest.json"), {
        "schema": EXPECTED_RESULT_SCHEMA,
        "run": {"status": "completed", "expected_rows": 4 * len(chosen), "completed_rows": len(combined)},
        "output": {"csv_bytes": output.stat().st_size, "csv_sha256": sha(output)},
        "comparison": {"paired_conditions": len(chosen), "methods": ["DSDA", "RBFOpt", "BAM 5.0.0", METHOD],
                       "baselines": inputs, "fmqa_csv_sha256": sha(fmqa_csv), "fmqa_protocol": run,
                       "timing_scope": "Completed lookup runs; no original GDP/NLP solve cost included"}})
    load_case_study_results(output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fmqa-results", type=Path, required=True, help="Run directory, CSV, or result ZIP")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--time-profiles", action="store_true",
                        help="Also plot completion time; only interpret under comparable Dantzig execution conditions")
    args = parser.parse_args()
    environment()
    from benchmark_analysis import METHOD_COLORS
    from case_study_analysis import create_case_study_analysis_outputs
    METHOD_COLORS.update({"BAM 5.0.0": "#2ca02c", METHOD: "#9467bd"})
    try:
        with result_directory(args.fmqa_results) as directory:
            output = combine(directory, args.output_dir)
        create_case_study_analysis_outputs(results_csv=output, output_dir=args.output_dir)
        if args.time_profiles:
            from timing_analysis import create_timing_outputs
            create_timing_outputs("case", output_dir=args.output_dir / "timing", results_csv=output)
        print(f"COMPARISON_DIR={args.output_dir.resolve()}")
        print("Timing is full lookup-run completion time, not GDP/NLP time or measured first-hit time.")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
