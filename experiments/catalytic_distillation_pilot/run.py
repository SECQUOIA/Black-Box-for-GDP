"""Pilot of the catalytic distillation configuration space with a fixed NLP initialization.

Every sampled configuration is solved from the same initialization file, so each
response is independent of the order of evaluation.  The pilot reports solver
statuses, solve times, and the best objective found, which decide whether the
space can be enumerated for a lookup benchmark.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import signal
import statistics
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
MODEL = REPO / "gdp_models/catalytic_distillation"
STAGES = range(2, 22)  # the reflux returns to stage 2; stage 22 is the reboiler
PUBLISHED = (4, 4, 6, 8, 8, 10)  # D-SDA optimum in dsda-gdp, zobj = 22631.7829089
INITIAL = (3, 4, 5, 6, 8, 9)  # configuration of the model file and init.gdx
FIELDS = ("f1", "c1", "c2", "c3", "f2", "b")
OPERATION = ("Qr", "Qc", "RR", "BR", "D", "Htotal", "xETBE", "Lmax", "Vmax")


def admissible():
    """All configurations with 2 <= f1 <= c1 < c2 < c3 <= f2 <= b <= 21."""
    return [(f1, c1, c2, c3, f2, b)
            for f1 in STAGES for c1 in range(f1, 22) for c2 in range(c1 + 1, 22)
            for c3 in range(c2 + 1, 22) for f2 in range(c3, 22) for b in range(f2, 22)]


def solve(config, gams, solver, timeout, init=MODEL / "init", model=MODEL / "distillation_model.gms", threads=1):
    args = [f"--{k}={v}" for k, v in zip(FIELDS, config)]
    with tempfile.TemporaryDirectory() as work:
        started = time.perf_counter()
        # GAMS runs the solver in a child process; a new session lets a timeout kill both.
        proc = subprocess.Popen(
            [gams, str(MODEL / "solve_configuration.gms"), *args, f"--solver={solver}",
             f"--model={model}", f"--init={init}", "--out=result.txt", f"curDir={work}", "lo=0",
             f"threads={threads}"],
            cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            returncode = "timeout"
        wall = time.perf_counter() - started
        text = Path(work, "result.txt").read_text() if Path(work, "result.txt").exists() else ""
    values = dict(re.findall(r"(\w+)=(\S+)", text))
    row = dict(zip(FIELDS, config), solver=solver, returncode=returncode, wall_s=wall)
    for key, kind in [("modelstat", int), ("solvestat", int), ("zobj", float), ("resusd", float)]:
        row[key] = kind(values[key]) if key in values else None
    row.update({key: float(values[key]) if key in values else None for key in OPERATION})
    return row


def accepted(row):
    """Locally optimal (2) or optimal (1) with normal completion."""
    return row["solvestat"] == 1 and row["modelstat"] in (1, 2)


def main(argv=None):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261031)
    parser.add_argument("--solver", default="conopt")
    parser.add_argument("--init", default=str(MODEL / "init"), help="GDX initialization, without extension")
    parser.add_argument("--model", default=str(MODEL / "distillation_model.gms"), help="model file to include")
    parser.add_argument("--configs", help="CSV with columns f1,c1,c2,c3,f2,b to solve instead of a random sample")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--threads", type=int, default=1, help="solver threads per solve")
    parser.add_argument("--gams", default=os.environ.get("GAMS_EXE") or shutil.which("gams"))
    parser.add_argument("--output", default=str(REPO / f"results/catalytic_distillation_pilot_{stamp}"))
    args = parser.parse_args(argv)
    if not args.gams:
        raise SystemExit("GAMS not found; pass --gams or set GAMS_EXE")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    space = admissible()
    if args.configs:
        with open(args.configs, newline="") as f:
            sample = [tuple(int(r[k]) for k in FIELDS) for r in csv.DictReader(f)]
        if not set(sample) <= set(space):
            raise SystemExit("--configs contains inadmissible configurations")
    else:
        rng = random.Random(args.seed)
        sample = [PUBLISHED, INITIAL] + rng.sample([c for c in space if c not in (PUBLISHED, INITIAL)], args.samples)
    started = time.perf_counter()
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(lambda c: solve(c, args.gams, args.solver, args.timeout, args.init, args.model, args.threads), sample))
    elapsed = time.perf_counter() - started
    with (output / "solves.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    ok = [r for r in rows if accepted(r)]
    times = [r["resusd"] for r in rows if r["resusd"] is not None]
    best = min(ok, key=lambda r: r["zobj"]) if ok else None
    published = next((r for r in rows if tuple(r[k] for k in FIELDS) == PUBLISHED), None)
    summary = dict(
        admissible_configurations=len(space), sampled=len(sample), seed=None if args.configs else args.seed,
        configs=args.configs, solver=args.solver, init=args.init, model=args.model, threads=args.threads,
        accepted=len(ok),
        statuses={f"{m}/{s}": sum((r["modelstat"], r["solvestat"]) == (m, s) for r in rows)
                  for m, s in sorted({(r["modelstat"], r["solvestat"]) for r in rows}, key=str)},
        timeouts=sum(r["returncode"] == "timeout" for r in rows),
        solver_seconds=dict(median=statistics.median(times), max=max(times)) if times else None,
        wall_seconds_median=statistics.median(r["wall_s"] for r in rows),
        published=published,
        best=best,
        better_than_published=[r for r in ok if r["zobj"] < published["zobj"] - 1e-6] if published and accepted(published) else None,
        campaign_seconds=elapsed, workers=args.workers,
        host=platform.node(), gams=args.gams,
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("better_than_published",)}, indent=2))
    print("better than published:", summary["better_than_published"] and len(summary["better_than_published"]))


if __name__ == "__main__":
    main()
