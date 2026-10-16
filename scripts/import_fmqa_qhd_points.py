"""Import the 96 Dantzig rejection measurements and refresh QHD point joins."""

# ruff: noqa: E402 -- permit direct execution from the repository root

import argparse
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fmqa_qhd_point_runner import plan, valid_record
from overnight_benchmark.common import read, save, sha, THREADS
from scripts.import_small_batch_full_domain import verify_archive
from scripts.import_fmqa_qhd import OUTPUT, ARCHIVE_NAME, build


def import_points(archive):
    with tempfile.TemporaryDirectory(prefix="fmqa_points_import_") as temp:
        directory = Path(temp)
        verified = verify_archive(archive, directory)
        run, summary = read(directory / "run.json"), read(directory / "summary.json")
        if (run["plan"] != plan() or not summary["all_completed"] or summary["completed_points"] != 96
                or run["host"] != "dantzig.ecn.purdue.edu" or run["versions"]["pyomo"] != "6.10.0"
                or any(run["thread_environment"].get(k) != v for k, v in THREADS.items())
                or run["affinity"]["effective_cpus"] != [run["cpu"]]):
            raise ValueError("Point completion/runtime/plan mismatch")
        for name, digest in run["source_sha256"].items():
            if sha(directory / "source" / name) != digest:
                raise ValueError("Point source checksum mismatch")
            if name.startswith("gdp_models/") and sha(ROOT / name) != digest:
                raise ValueError("Original GDP evaluation implementation changed")
        if (run["upstream"]["commit"] != "3e469dbeea8931670b8cd6752014ab7a767d3af5"
                or any(sha(ROOT / "external/dsda-gdp" / name) != digest for name, digest in run["upstream"]["files_sha256"].items())):
            raise ValueError("Original model/initialization sources changed")
        points = []
        for spec in run["plan"]:
            folder = directory / "jobs" / spec["job_id"]
            result = folder / "result.json"
            if sha(result) != read(folder / "complete.json")["result_sha256"]:
                raise ValueError("Point completion seal mismatch")
            record = valid_record(read(result), spec)
            points.append({**record, "source_member": directory.name + "/" + result.relative_to(directory).as_posix(),
                           "source_sha256": sha(result)})
        destination = ROOT / "results/archives" / archive.name
        if destination.exists() and sha(destination) != sha(archive):
            raise ValueError("Refusing to replace an existing archive")
        if destination.resolve() != archive.resolve():
            shutil.copy2(archive, destination)
        destination.with_suffix(".zip.sha256").write_text(f"{sha(destination)}  {destination.name}\n")
        # ZIP root is the original run-directory name, not the extraction directory.
        import zipfile
        with zipfile.ZipFile(archive) as z:
            prefix = z.namelist()[0].split('/')[0]
        for row in points:
            row["source_member"] = prefix + '/' + row["source_member"].split('/', 1)[1]
        save(OUTPUT / "point_supplement.json", {"archive": str(destination.relative_to(ROOT)),
            "archive_sha256": sha(destination), "verified_members": verified, "runtime": run,
            "points": points, "measured_points": len(points)})
    build(ROOT / "results/archives" / ARCHIVE_NAME)
    from scripts.plot_dantzig_cost_breakdown import OUTPUT as FIGURES, build as costs
    from scripts.plot_dantzig_performance import build as performance
    costs(FIGURES)
    performance()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    import_points(parser.parse_args().archive)
