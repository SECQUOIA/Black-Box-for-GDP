"""Grid-only FMQA-SA entry point; all process-model cases are excluded."""

import sys

from fmqa_benchmark_runner import main


if __name__ == "__main__":
    if any(arg == "--dataset" or arg.startswith("--dataset=") for arg in sys.argv[1:]):
        raise SystemExit("This entry point always uses QHDOpt grids; omit --dataset.")
    sys.argv.extend(["--dataset", "grid"])
    raise SystemExit(main())
