"""Small, standard-library helpers shared by the builder and controller."""

import csv
import hashlib
import json
import math
from pathlib import Path


METHODS = (
    "rbfopt_msrsm_genetic",
    "uniform_without_replacement",
    "bam_predetermined_uniform",
)
THREADS = {
    k: "1"
    for k in (
        "OMP_NUM_THREADS",
        "OMP_THREAD_LIMIT",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    )
}
THREADS.update(OMP_DYNAMIC="FALSE", MKL_DYNAMIC="FALSE")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "tolist"):
        return clean(value.tolist())
    return value


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(clean(value), indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def csvrows(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def writecsv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {
                k: json.dumps(v) if isinstance(v, (list, dict)) else v
                for k, v in r.items()
            }
            for r in rows
        )


def verify(root):
    inventory = read(root / "inventory.json")
    for name, digest in inventory["files_sha256"].items():
        if not (root / name).is_file() or sha(root / name) != digest:
            raise ValueError(f"Package input/source changed: {name}")
    return sha(root / "inventory.json")


def delta(before, after):
    return {
        k: [before.get(k), after.get(k)]
        for k in before.keys() | after.keys()
        if before.get(k) != after.get(k)
    }


def check_settings(before, after):
    difference = delta(before, after)
    if difference != {"global_search_method": ["solver", "genetic"]}:
        raise ValueError(f"Unexpected settings difference: {difference}")
    return difference
