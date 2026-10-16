"""Small persistence primitives shared by the overnight workers and reports."""

from datetime import datetime, timezone
import csv
import hashlib
import json
import os
from pathlib import Path

from evaluation_trace import safe_json

ROOT = Path(__file__).resolve().parents[1]
KIND = "dantzig_dfo_trace_point_timing_v1"
METHODS = ("dsda", "rbfopt", "bam")
THREADS = {k: "1" for k in (
    "OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as stream:
        json.dump(safe_json(value), stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def append(path, value):
    with Path(path).open("a") as stream:
        stream.write(json.dumps(safe_json(value), allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def jsonl(path):
    if not Path(path).exists():
        return []
    # Only a torn final line is recoverable after a machine/process interruption.
    raw = Path(path).read_bytes()
    lines = raw.splitlines(keepends=True)
    records = []
    for i, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1 or line.endswith(b"\n"):
                raise
    return records


def csv_file(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v
                             for k, v in safe_json(row).items()})
    temporary.replace(path)


def point_key(case, size, point):
    return (case, size if case == "cstr" else None, tuple(point))


def point_spec(key):
    case, size, point = key
    return {"case_name": case, "grid_size": size, "point": list(point),
            "job_id": f"{case}_{size or 0}_" + "_".join(map(str, point))}


def source_files():
    files = []
    for name in ("overnight_benchmark", "gdp_models", "case_studies", "case_study_data",
                 "fmqa_benchmark/reference", "benchmark_grids"):
        files.extend(p for p in (ROOT / name).rglob("*") if p.is_file()
                     and not any(x.startswith(".") or x == "__pycache__"
                                 for x in p.relative_to(ROOT).parts)
                     and p.suffix != ".pyc" and p.name != "comparison.py")
    files.extend(ROOT / name for name in (
        "benchmark.py", "grid_dsda.py", "grid_rbfopt.py",
        "instrumentation.py", "evaluation_trace.py", "case_study_benchmark.py",
        "cpu_affinity.py", "run_dfo_trace_nlp_dantzig.sh", "requirements-dfo-trace-nlp.txt",
        "fmqa_benchmark/__init__.py", "fmqa_benchmark/protocol.py",
        "LICENSE", "docs/dfo_trace_nlp_dantzig.md"))
    return sorted(set(files))


def source_hashes():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in source_files()}
