"""Regenerate three-method time profiles with the archived BAM 5.0.0 rerun."""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt
import pandas as pd

import benchmark_analysis as ba
import timing_analysis as ta

BASELINE = Path("results/archives/dantzig_20260910_170759_slN8tv.zip")
BAM = Path("dantzig_bam_20260916_231228_FNzbAA.zip")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def archived_json(archive, basename):
    with zipfile.ZipFile(ROOT / archive) as source:
        members = [name for name in source.namelist() if Path(name).name == basename]
        if len(members) != 1:
            raise ValueError(f"Expected one {basename} in {archive}")
        return json.loads(source.read(members[0]))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    audit = archived_json(BAM, "comparison_audit.json")
    version = archived_json(BAM, "bam-version.json")
    require(version["package"] == "5.0.0", "Expected BAM 5.0.0")
    old_manifest = archived_json(BASELINE, "process_case_studies.manifest.json")
    new_manifest = archived_json(BAM, "process_case_studies.manifest.json")
    for field in ("data_files_sha256", "initial_design"):
        require(
            old_manifest["provenance"][field] == new_manifest["provenance"][field],
            f"Process provenance mismatch: {field}",
        )
    require(
        old_manifest["protocol"]["case_parameters"]
        == new_manifest["protocol"]["case_parameters"],
        "Case parameters differ",
    )
    require(
        old_manifest["provenance"]["source_files_sha256"].items()
        >= new_manifest["provenance"]["source_files_sha256"].items(),
        "Benchmark source files differ",
    )
    ba.configure_plot_style()
    ba.METHOD_COLORS["BAM 5.0.0"] = ba.METHOD_COLORS["BAM"]

    for dataset, expected in (("grid", 1050), ("case", 139)):
        loaded, sources = {}, {}
        for tag, archive in (("baseline", BASELINE), ("bam_5.0.0", BAM)):
            loaded[tag], sources[tag] = ta._load_input(
                dataset, None, ROOT / archive, ROOT / "benchmark_grids"
            )
            sources[tag]["archive"] = archive.as_posix()
            if dataset == "case":
                require(loaded[tag].attrs["input_validation"]["verified"], "Unverified case CSV")
        basename = "benchmark.csv" if dataset == "grid" else "process_case_studies.csv"
        require(
            sources["baseline"]["csv_sha256"] == audit[f"reference_{dataset}_csv_sha256"],
            "Baseline CSV does not match the comparison audit",
        )
        require(
            sources["bam_5.0.0"]["csv_sha256"] == audit[f"{basename}_sha256"],
            "New BAM CSV does not match the comparison audit",
        )
        old, new = loaded["baseline"], loaded["bam_5.0.0"]
        require(set(old.method) == {"DSDA", "RBFOpt", "BAM"}, "Unexpected baseline methods")
        require(set(new.method) == {"BAM"}, "Expected a BAM-only rerun")
        require(len(old) == 3 * expected and len(new) == expected, "Unexpected row counts")
        old_bam = old.loc[old.method == "BAM"].set_index(ta.INSTANCE_COLUMNS).sort_index()
        new_bam = new.set_index(ta.INSTANCE_COLUMNS).sort_index()
        require(old_bam.index.is_unique and new_bam.index.is_unique, "Duplicate BAM keys")
        require(old_bam.index.equals(new_bam.index), "BAM run keys differ")
        require(old_bam.target_value.equals(new_bam.target_value), "BAM targets differ")
        # Preserve all DSDA/RBFOpt rows; replace the entire BAM version at once.
        retained = old.loc[old.method != "BAM"].copy()
        replacement = new.copy()
        replacement["method"] = "BAM 5.0.0"
        retained.attrs = {}
        replacement.attrs = {}
        data = ta.prepare_timing_data(pd.concat([retained, replacement], ignore_index=True))
        require(len(data) == 3 * expected, "Unexpected combined row count")
        summary = ta.timing_summary(data, dataset)
        folder = OUTPUT / dataset
        folder.mkdir(parents=True, exist_ok=True)
        columns = ta.INSTANCE_COLUMNS + [
            "method", "target_value", "best_value", "tolerance", "solved",
            "wall_time_s", "successful_run_time_s", "time_ratio",
        ]
        data[columns].to_csv(folder / "time_profile_runs.csv", index=False)
        summary.to_csv(folder / "time_work_summary.csv", index=False)
        figure = ta.plot_time_profiles(data, dataset)
        figure.savefig(folder / "time_performance_profiles.png", dpi=250, bbox_inches="tight")
        plt.close(figure)
        provenance = {
            "dataset": dataset,
            "sources": sources,
            "method_sources": {"DSDA": "baseline", "RBFOpt": "baseline", "BAM 5.0.0": "bam_5.0.0"},
            "bam_version": version,
            "n_runs": len(data),
            "paired_instances": expected,
            "tolerance": ba.PRIMARY_TOLERANCE,
            "success_rule": "abs(best_value - target_value) <= tolerance * max(1, abs(target_value))",
            "time_measure": "full recorded successful-run wall time; failures have infinite cost",
            "first_hit_timestamps_available": False,
            "ratio_methods": ["DSDA", "RBFOpt", "BAM 5.0.0"],
            "checks": {
                "run_keys_match": True,
                "targets_match": True,
                "source_csv_hashes_match_comparison_audit": True,
                "process_initial_design_and_data_match": True,
                "shared_benchmark_source_hashes_match": True,
                "dsda_rbfopt_rows_retained_without_changes": True,
            },
            "source_sha256": {
                str(path.relative_to(ROOT)): sha256(path)
                for path in (
                    Path(__file__).resolve(), ROOT / "timing_analysis.py",
                    ROOT / "benchmark_analysis.py", ROOT / "case_study_analysis.py",
                )
            },
            "python": platform.python_version(),
            "packages": {
                name: importlib.metadata.version(name)
                for name in ("numpy", "pandas", "matplotlib", "scipy")
            },
        }
        if dataset == "grid":
            provenance["grid_sha256"] = {
                name: sha256(ROOT / "benchmark_grids" / name)
                for name in sorted(data.csv_name.unique())
            }
        (folder / "timing_analysis.manifest.json").write_text(
            json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{dataset}: {len(data)} runs; saved {folder.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
