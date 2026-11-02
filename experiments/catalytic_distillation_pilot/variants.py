"""Variants of the catalytic distillation model with single findings of REVIEW.md fixed.

The variants are diagnostic copies; the vendored model stays as published.

  single_af               finding 11: tray and shell costs annualized once
  etbe_revenue            finding 15: revenue from the ETBE in the bottoms only
  single_af_etbe_revenue  findings 11 and 15
  wide_bounds             finding 27: operating bounds on Qr, Qc, RR, BR, L, and V widened

Writes the variant models and, unless --models-only, solves the given configurations
under the published model and the three objective variants.
"""

import argparse
import csv
from pathlib import Path

from run import MODEL, PUBLISHED, accepted, solve

ANNUALIZE_ONCE = [("CT=AF*(MS/280)", "CT=(MS/280)"), ("Csh=AF*(MS/280)", "Csh=(MS/280)")]
ETBE_REVENUE = [("(CostB*L('1','1',Net))", "(CostB*L('1','1',Net)*x('1','1','ETBE',Net)/100)")]
WIDE_BOUNDS = [
    ("Qr.up(N,j)=400;", "Qr.up(N,j)=2000;"),
    ("Qr.lo(N,j)=100;", "Qr.lo(N,j)=10;"),
    ("Qc.up(N,j)=900;", "Qc.up(N,j)=5000;"),
    ("RR.up(N,j)=10;", "RR.up(N,j)=50;"),
    ("BR.up(N,j)=10;", "BR.up(N,j)=50;"),
    ("L.up(N,j,Net)=200;", "L.up(N,j,Net)=1000;"),
    ("V.up(N,j,Net)=200;", "V.up(N,j,Net)=1000;"),
]
VARIANTS = {
    "single_af": ANNUALIZE_ONCE,
    "etbe_revenue": ETBE_REVENUE,
    "single_af_etbe_revenue": ANNUALIZE_ONCE + ETBE_REVENUE,
    "wide_bounds": WIDE_BOUNDS,
}
OBJECTIVE_VARIANTS = ("published", "single_af", "etbe_revenue", "single_af_etbe_revenue")
CONFIGS = [PUBLISHED, (7, 7, 11, 17, 17, 20), (12, 12, 16, 18, 18, 20)]


def write_variants(directory):
    source = (MODEL / "distillation_model.gms").read_text()
    paths = {"published": MODEL / "distillation_model.gms"}
    for name, replacements in VARIANTS.items():
        text = source
        for old, new in replacements:
            if text.count(old) != 1:
                raise SystemExit(f"{name}: expected one occurrence of {old!r}")
            text = text.replace(old, new)
        paths[name] = directory / f"{name}.gms"
        paths[name].write_text(text)
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", required=True)
    parser.add_argument("--gams", required=True)
    parser.add_argument("--solver", default="conopt")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--models-only", action="store_true")
    args = parser.parse_args(argv)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    paths = write_variants(output)
    if args.models_only:
        return
    rows = []
    for variant in OBJECTIVE_VARIANTS:
        for config in CONFIGS:
            row = solve(config, args.gams, args.solver, args.timeout, model=paths[variant])
            rows.append(dict(variant=variant, accepted=accepted(row), **row))
            print(variant, config, row["modelstat"], row["zobj"], row["xETBE"], flush=True)
    with (output / "objective_variants.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
