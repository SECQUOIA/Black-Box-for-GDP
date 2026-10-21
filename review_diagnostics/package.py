"""Bundle diagnostic tools for an existing checkout; includes no solver or benchmark data."""

import argparse
from pathlib import Path
import zipfile

from .common import ROOT, sha


def build(output):
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted((ROOT / "review_diagnostics").glob("*.py"))
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            z.write(path, "review_diagnostics_runner/" + str(path.relative_to(ROOT)))
        z.write(
            ROOT / "results/review_diagnostics_20261020/README.md",
            "review_diagnostics_runner/README.md",
        )
        z.writestr(
            "review_diagnostics_runner/FILES.sha256",
            "".join(f"{sha(p)}  {p.relative_to(ROOT)}\n" for p in files),
        )
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{sha(output)}  {output.name}\n"
    )
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    print(build(p.parse_args().output.resolve()))


if __name__ == "__main__":
    main()
