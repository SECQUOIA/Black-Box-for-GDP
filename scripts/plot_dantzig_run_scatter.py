"""Update the published individual-run scatter and its legacy figure URLs.

Run: python -m scripts.plot_dantzig_run_scatter
No optimizer or NLP solver is executed.
"""

import argparse
from pathlib import Path

from scripts.plot_dantzig_cost_breakdown import OUTPUT
from scripts.plot_dantzig_performance import build_run_scatter


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    build_run_scatter(parser.parse_args().output_dir)
