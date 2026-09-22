"""Command-line evaluation of one original GDP subproblem."""

import argparse
import contextlib
import json
import logging
from pathlib import Path
import sys

from .evaluation import evaluate_point
from .models import MODELS
from .solvers import SOLVERS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=MODELS, required=True)
    parser.add_argument("--point", required=True, help="Comma-separated integer coordinates")
    parser.add_argument("--cstr-size", type=int, default=5)
    parser.add_argument("--solver", choices=SOLVERS, required=True)
    parser.add_argument("--executable", help="Path to IPOPT or the GAMS executable")
    parser.add_argument("--initialization", choices=("auto", "saved", "default"), default="auto")
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--tee", action="store_true", help="Send solver output to stderr")
    parser.add_argument("--output", type=Path, help="Also write the JSON report to this file")
    args = parser.parse_args()
    # Pyomo binds its default logging stream at import time, before
    # redirect_stdout can take effect. Keep diagnostics out of JSON stdout.
    for handler in logging.getLogger("pyomo").handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
            handler.setStream(sys.stderr)
    try:
        # Upstream/Pyomo notices must not corrupt stdout's JSON record.
        with contextlib.redirect_stdout(sys.stderr):
            report = evaluate_point(
                args.case, args.point.split(","), solver=args.solver,
                cstr_size=args.cstr_size, initialization=args.initialization,
                time_limit=args.time_limit, executable=args.executable, tee=args.tee,
            )
    except (ValueError, FileNotFoundError, RuntimeError) as error:
        parser.exit(2, f"{error}\n")
    rendered = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
