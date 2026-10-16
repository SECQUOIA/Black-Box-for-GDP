"""Verify/replay the final Process artifacts without optimization or NLP calls.

All generated files go to a new --output directory. Historical reports,
recorded revisions, figures, archives and runner packages remain untouched.
"""

import argparse
from collections import Counter, defaultdict
import copy
import csv
import gzip
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "results/process_ipopt_bam_v2_20261015"
MANIFEST = RESULT / "integration/manifest.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", newline="") as stream:
        return list(csv.DictReader(stream))


def verify_preservation(manifest):
    """Match pre-merge bytes either in the tree or PR #23's original ZIPs."""
    baseline_path = ROOT / manifest["before_inventory"]["path"]
    require(sha(baseline_path) == manifest["before_inventory"]["sha256"], "Baseline inventory changed")
    with gzip.open(baseline_path, "rt") as stream:
        baseline = json.load(stream)
    changed, missing, retained = [], {}, 0
    for name, old in baseline["files"].items():
        path = ROOT / name
        if not path.is_file():
            missing[name] = old
        elif sha(path) != old["sha256"]:
            require(name in manifest["documented_nondata_changes"], f"Original artifact changed: {name}")
            changed.append(name)
        else:
            retained += 1
    import result_archives as storage
    archived = []
    for entry in storage.datasets().values():
        prefix = entry["directory"] + "/"
        candidates = [name for name in missing if name.startswith(prefix)]
        if not candidates:
            continue
        index = {}
        if "trace_index" in entry:
            index = {r["trajectory_path"]: r["archive_trace_path"]
                     for r in rows(ROOT / entry["directory"] / entry["trace_index"])}
        with storage.verified_zip(entry) as (archive, _):
            for name in candidates:
                relative = name[len(prefix):]
                member = entry["archive_root"] + "/" + index.get(relative, relative)
                data = archive.read(member)
                require(hashlib.sha256(data).hexdigest() == missing[name]["sha256"],
                        f"Removed copy differs from archive: {name}")
                archived.append(name)
                del missing[name]
    require(not missing, f"Missing original artifacts: {list(missing)[:10]}")
    for name, expected in manifest["additional_files_sha256"].items():
        require(sha(ROOT / name) == expected, f"Additional artifact changed: {name}")
    return {"baseline_files": len(baseline["files"]), "unchanged_files_in_tree": retained,
            "unchanged_original_archives": sum(name.endswith((".zip", ".tar.gz"))
                                               for name in baseline["files"]),
            "byte_identical_copies_in_original_archives": len(archived),
            "documented_documentation_or_verifier_changes": changed,
            "missing_or_changed_experimental_artifacts": 0}


def verify_sources(manifest):
    original = read(RESULT / "source_manifest.json")
    for name, expected in original["sources"].items():
        require(sha(ROOT / name) == expected["sha256"], f"Analysis input changed: {name}")
    for name, digest in manifest["analysis_files_sha256"].items():
        require(sha(ROOT / name) == digest, f"Historical analysis code changed: {name}")
    for name, digest in read(RESULT / "figure_manifest.json")["files"].items():
        require(sha(RESULT / "figures" / name) == digest, f"Published figure changed: {name}")
    counts = {}
    for dataset in manifest["datasets"]:
        archive_path = ROOT / dataset["archive"]
        require(sha(archive_path) == dataset["archive_sha256"], f"Return ZIP changed: {archive_path}")
        inventory = read(ROOT / dataset["member_inventory"])
        with zipfile.ZipFile(archive_path) as archive:
            require(archive.testzip() is None, f"ZIP CRC failure: {archive_path}")
            names = [m.filename for m in archive.infolist() if not m.is_dir()]
            expected_names = {dataset["archive_root"] + "/" + n for n in inventory}
            require(len(names) == len(set(names)) and set(names) == expected_names,
                    f"Return member inventory differs: {archive_path}")
            for name, digest in inventory.items():
                require(hashlib.sha256(archive.read(dataset["archive_root"] + "/" + name)).hexdigest() == digest,
                        f"Return member changed: {name}")
        counts[dataset["id"]] = len(inventory)
        if "runner" in dataset:
            require(sha(ROOT / dataset["runner"]) == dataset["runner_sha256"], "Submitted runner changed")
    return {"analysis_inputs_verified": len(original["sources"]), "archive_members_verified": counts}


def verify_bam(core):
    count, slots, differences = 0, 0, Counter()
    for kind in ("cstr", "non_cstr"):
        old, new = core.DATA[kind], core.DATA[kind + "_bam"]
        old_jobs = {r["job_id"]: r for r in read(old / "job_metadata.json")}
        new_jobs = {r["job_id"]: r for r in read(new / "job_metadata.json")}
        old_events, new_events = defaultdict(list), defaultdict(list)
        for event in rows(old / "callbacks.csv.gz"):
            old_events[event["job_id"]].append(event)
        for event in rows(new / "callbacks.csv.gz"):
            new_events[event["job_id"]].append(event)
        for job, current in new_jobs.items():
            require(current["spec"]["method"] == "bam", "Non-BAM replacement")
            prior = old_jobs[job]
            for field in ("spec", "settings"):
                lhs, rhs = copy.deepcopy(prior[field]), copy.deepcopy(current[field])
                policy = rhs["settings"] if field == "spec" else rhs
                require(policy.pop("budget_stop_policy") == "native_max_evals_return_terminal_v2",
                        f"Unexpected BAM policy: {job}")
                require(lhs == rhs, f"BAM configuration changed beyond stop policy: {job}/{field}")
            budget = current["spec"]["budget"]
            before = sorted(old_events[job], key=lambda e: int(e["index"]))[:budget]
            after = sorted(new_events[job], key=lambda e: int(e["index"]))
            require(len(before) == len(after) == budget, f"BAM budget mismatch: {job}")
            for left, right in zip(before, after):
                for field in ("index", "point", "accepted", "raw_objective", "selected_attempt_nlp_s"):
                    require(left[field] == right[field], f"BAM evaluation changed: {job}/{field}")
                require(core.yes(right["value_returned_to_optimizer"]), f"Undelivered terminal value: {job}")
                count += 1
            differences["recorded_dfo_wall_time_changed"] += (
                prior["result"]["dfo_wall_s"] != current["result"]["dfo_wall_s"])
            slots += 1
    require((slots, count) == (140, 3430), "Incomplete BAM replacement")
    return {"bam_runs": slots, "identical_bam_callbacks": count,
            "configuration_difference": "budget_stop_policy only",
            "runtime_differences_expected_from_rerun": dict(differences)}


def replay(output, figures=False):
    """Execute only saved-record analysis, writing into a new directory."""
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".mplcache"))
    sys.path.insert(0, str(ROOT / "scripts/process_ipopt"))
    core = importlib.import_module("analysis_core")
    core.OUT = output
    core.SOURCES.clear()
    refresh = importlib.import_module("refresh")
    refresh.OUT = output
    runs, events, _, _, groups, summary = refresh.load()
    require(summary["outcomes"] == {"target_reached": 291, "target_not_reached": 268, "execution_failed": 1},
            "Final outcomes differ from the recorded comparison")
    require(len(runs) == 560 and len(events) == 12822, "Incomplete final selection")
    require(sum(r["result_batch"].endswith("_bam") for r in runs) == 140, "Wrong BAM selection")
    require(all(r["result_batch"].endswith("_bam") == (r["method"] == "bam") for r in runs),
            "Mixed old/new BAM selection")
    require(all(r["reconstructed_total_s"] is not None for r in runs), "Missing reconstructed cost")
    require(summary["tts_statuses"] == {"available": 54, "zero_observed_hits": 2}, "TTS99 counts changed")
    regenerated = sorted((output / "tables").glob("*.csv"))
    for path in regenerated:
        require(path.read_bytes() == (RESULT / "tables" / path.name).read_bytes(),
                f"Regenerated table differs: {path.name}")
    old_summary = read(RESULT / "timing_audit.json")
    require({k: v for k, v in summary.items() if k != "repository_head"} ==
            {k: v for k, v in old_summary.items() if k != "repository_head"}, "Timing summary changed")
    bam = verify_bam(core)
    if figures:
        plot = importlib.import_module("build_figures")
        plot.build(runs, groups)
    return {"runs": len(runs), "outcomes": summary["outcomes"], "callbacks": len(events),
            "selected_bam": bam, "tables_reproduced_byte_for_byte": [p.name for p in regenerated],
            "complete_cost_runs": summary["timed_protocol_valid_runs"],
            "supplemented_callbacks": summary["supplemented_callbacks"],
            "remaining_time_gaps": summary["remaining_in_budget_time_gaps"],
            "tts99": summary["tts_statuses"],
            "historical_analysis_revision": old_summary["repository_head"],
            "figures_regenerated": figures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory for verification/replay outputs")
    parser.add_argument("--figures", action="store_true", help="Also regenerate figures (numpy/matplotlib required)")
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists(), "Refusing to overwrite an existing output directory")
    require(not output.is_relative_to(ROOT / "results"), "Replay output must be outside retained results")
    require(sys.flags.optimize == 0, "Do not disable the historical analysis assertions with python -O")
    sys.path.insert(0, str(ROOT))
    manifest = read(MANIFEST)
    preservation = verify_preservation(manifest)
    sources = verify_sources(manifest)
    output.mkdir(parents=True)
    report = {"status": "PASS", "preservation": preservation, "sources": sources,
              "replay": replay(output, args.figures),
              "artifact_source_revision": manifest["source_revision"],
              "integrated_main_revision": manifest["integrated_main_revision"],
              "provider_revision_at_verification": subprocess.check_output(
                  ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "verification_script_sha256": sha(__file__),
              "new_optimization_or_nlp_experiments": False}
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
