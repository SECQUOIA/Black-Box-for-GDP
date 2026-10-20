"""Regenerate manuscript figures/tables from frozen records without optimizers."""

import argparse
from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import platform
import subprocess
import sys

from common import ROOT, sha, write_json
from tables import generate
from verify import verify, verify_figure8


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New, empty output directory"
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Also replay archived Grid/Process analyses and evaluate saved GDP vectors; never solve",
    )
    parser.add_argument("--tables-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output must be empty: retained data must not be overwritten")
    if (
        output == ROOT
        or output.is_relative_to(ROOT / "results")
        or output.is_relative_to(ROOT / "reproduction")
    ):
        parser.error(
            "Use a separate output directory outside retained results and reproduction sources"
        )
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(output / "mplconfig"))
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "dependencies": {
            n: importlib.metadata.version(n)
            for n in ["numpy", "scipy", "pandas", "matplotlib", "pyomo"]
        },
        "command": sys.argv,
        "status": "running",
        "public_release": "pending",
        "logged_out_access": "not_performed",
        "commands": [],
    }
    report["source_sha256"] = {
        str(p.relative_to(ROOT)): sha(p)
        for p in sorted((ROOT / "reproduction").rglob("*.py"))
    }
    package_manifest = ROOT / "PACKAGE_MANIFEST.json"
    if package_manifest.is_file():
        from common import read_json

        report["provider_revision"] = read_json(package_manifest)["provider_revision"]
    elif (ROOT / ".git").exists():
        report["provider_revision"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    try:
        tables = generate(output / "tables")
        report["numerical_validation"] = verify(tables)
        if not args.tables_only:
            from figures import generate as figures

            report["figures"] = figures(output / "figures")
            report["figure8"] = verify_figure8(output / "figures/figure8_manifest.json")
        if args.replay:
            commands = [
                [
                    "scripts/verify_final_process.py",
                    "--output",
                    str(output / "process_replay"),
                ],
                [
                    "scripts/analyze_grid_gdp_paths.py",
                    "--output",
                    str(output / "grid_replay"),
                    "--no-figures",
                ],
                [
                    "gdp_current_analysis.py",
                    "--output",
                    str(output / "algebraic_replay"),
                ],
            ]
            for i, cmd in enumerate(commands):
                log = output / f"replay_{i + 1}.log"
                with log.open("w") as stream:
                    result = subprocess.run(
                        [sys.executable, *cmd],
                        cwd=ROOT,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                    )
                report["commands"].append(
                    {
                        "argv": [sys.executable, *cmd],
                        "exit_code": result.returncode,
                        "log": log.name,
                    }
                )
                if result.returncode:
                    raise RuntimeError(f"Replay failed: {cmd[0]}; see {log}")
            from verify import verify_replays

            report["replay_comparisons"] = verify_replays(output)
        report["tables"] = {k: len(v) for k, v in tables.items()}
        report["outputs"] = {
            str(p.relative_to(output)): sha(p)
            for p in sorted(output.rglob("*"))
            if p.is_file() and "mplconfig" not in p.parts
        }
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write_json(output / "validation.json", report)
    print(
        f"Validated {len(tables)} table datasets; report: {output / 'validation.json'}"
    )


if __name__ == "__main__":
    main()
