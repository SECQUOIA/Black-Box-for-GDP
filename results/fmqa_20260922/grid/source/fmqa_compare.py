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
from fmqa_benchmark_runner import GRID_KIND, KIND, environment, result_filename, result_record, save, validate_job


def load_results(path, dataset):
    from case_study_analysis import load_case_study_results, validate_case_study_manifest
    if dataset == "case":
        return load_case_study_results(path)
    from benchmark_analysis import load_benchmark_results
    frame = load_benchmark_results(path)
    validate_case_study_manifest(path, len(frame))
    return frame


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
    from instrumentation import RESULT_FIELDS
    directory = Path(directory)
    run = json.loads((directory / "run.json").read_text())
    dataset = run.get("dataset", "case")
    csv_path = directory / result_filename(run)
    manifest = json.loads(csv_path.with_suffix(".manifest.json").read_text())
    if run["kind"] != (GRID_KIND if dataset == "grid" else KIND) or manifest["fmqa_protocol"] != run:
        raise ValueError("FMQA run and CSV manifests do not match")
    if dataset == "grid":
        from fmqa_benchmark.grid_protocol import reference_grid_plan, verify_grid_sources
        expected_sources, expected_plan = verify_grid_sources(), reference_grid_plan()
    else:
        expected_sources, expected_plan = verify_lookup_sources(), reference_plan()
    if run["runtime"]["lookup_data_sha256"] != expected_sources:
        raise ValueError("FMQA and baseline lookup tables differ")
    frozen = {key(s): s for s in expected_plan}
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
    frame = load_results(csv_path, dataset)
    if len(frame) != len(plan) or set(frame["method"]) != {METHOD}:
        raise ValueError("FMQA CSV does not match the planned run count or method")
    by_key = {key(row): row for row in frame.to_dict("records")}
    if set(by_key) != {key(spec) for spec in plan}:
        raise ValueError("FMQA CSV contains missing or duplicate run keys")
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
    from case_study_analysis import EXPECTED_RESULT_SCHEMA
    from instrumentation import RESULT_FIELDS
    run = audit_fmqa(directory)
    dataset = run.get("dataset", "case")
    if json.loads((REFERENCE / "bam5-version.json").read_text())["package"] != "5.0.0":
        raise ValueError("Comparison requires BAM 5.0.0")
    chosen = {key(s) for s in run["plan"]}
    combined, inputs = [], {}
    for name, allowed in (("original", {"DSDA", "RBFOpt"}), ("bam5", {"BAM"})):
        if dataset == "grid":
            # audit_fmqa -> reference_grid_plan checked both baseline hashes,
            # all 4,200 run keys and their original three-value initial prefixes.
            from fmqa_benchmark.grid_protocol import GRID_REFERENCE
            path = GRID_REFERENCE / f"{name}.csv"
            audit_path = GRID_REFERENCE / "comparison_audit.json"
            inputs[name] = {"csv_sha256": sha(path), "comparison_audit_sha256": sha(audit_path)}
        else:
            path = REFERENCE / f"{name}.csv"
            load_results(path, dataset)
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
            inputs[name] = {"csv_sha256": sha(path), "manifest_sha256": sha(path.with_suffix(".manifest.json")),
                            "software": manifest.get("software")}
        selected = [r for r in rows(path) if r["method"] in allowed and key(r) in chosen]
        for method in allowed:
            if {key(r) for r in selected if r["method"] == method} != chosen:
                raise ValueError(f"Missing paired baseline runs: {method}")
        for row in selected:
            if row["method"] == "BAM":
                row["method"] = "BAM 5.0.0"
        combined.extend(selected)
    fmqa_csv = Path(directory) / result_filename(run)
    combined.extend(rows(fmqa_csv))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / result_filename(run)
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
        "comparison": {"dataset": dataset, "paired_conditions": len(chosen), "methods": ["DSDA", "RBFOpt", "BAM 5.0.0", METHOD],
                       "baselines": inputs, "fmqa_csv_sha256": sha(fmqa_csv), "fmqa_protocol": run,
                       "timing_scope": "Completed lookup runs; no original GDP/NLP solve cost included"}})
    load_results(output, dataset)
    return output


def grid_analysis(output, output_dir):
    from benchmark_analysis import (
        configure_plot_style, load_analysis_dataset, plot_performance_profiles,
        plot_convergence_curves, solved_fraction_summary,
    )
    from fmqa_benchmark.protocol import ROOT
    import matplotlib.pyplot as plt
    results, _ = load_analysis_dataset(output, grids_dir=ROOT / "benchmark_grids")
    configure_plot_style()
    solved_fraction_summary(results).to_csv(output_dir / "solved_fraction_summary.csv")
    for name, plot in (("evaluation_performance_profiles.png", plot_performance_profiles),
                       ("convergence_curves.png", plot_convergence_curves)):
        figure = plot(results)
        figure.savefig(output_dir / name, dpi=180, bbox_inches="tight")
        plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fmqa-results", type=Path, required=True, help="Run directory, CSV, or result ZIP")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dataset", choices=("case", "grid"), help="Require a particular dataset (otherwise infer from archive)")
    parser.add_argument("--time-profiles", action="store_true",
                        help="Also plot completion time; only interpret under comparable Dantzig execution conditions")
    args = parser.parse_args()
    environment()
    from benchmark_analysis import METHOD_COLORS
    from case_study_analysis import create_case_study_analysis_outputs
    METHOD_COLORS.update({"BAM 5.0.0": "#2ca02c", METHOD: "#9467bd"})
    try:
        with result_directory(args.fmqa_results) as directory:
            run = json.loads((directory / "run.json").read_text())
            dataset = run.get("dataset", "case")
            if args.dataset is not None and args.dataset != dataset:
                raise ValueError(f"Expected {args.dataset} results, received {dataset}")
            output = combine(directory, args.output_dir)
        if dataset == "grid":
            grid_analysis(output, args.output_dir)
        else:
            create_case_study_analysis_outputs(results_csv=output, output_dir=args.output_dir)
        if args.time_profiles:
            from timing_analysis import create_timing_outputs
            from fmqa_benchmark.protocol import ROOT
            create_timing_outputs(dataset, output_dir=args.output_dir / "timing", results_csv=output,
                                  grids_dir=ROOT / "benchmark_grids")
        print(f"COMPARISON_DIR={args.output_dir.resolve()}")
        print("Timing is full lookup-run completion time, not GDP/NLP time or measured first-hit time.")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
