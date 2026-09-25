"""Durable, opt-in objective-call traces for sequential process benchmarks.

The JSONL sidecar contains actual callbacks, including repeated points. Internal
solver cache accesses that do not call the objective are deliberately absent.
"""

from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
import uuid


ACTIVE_TRACE = ContextVar("objective_evaluation_trace", default=None)
TRACE_VERSION = 1


def finite_value(value):
    """Encode nonfinite numbers without ambiguous JSON NaN/Infinity tokens."""
    if value is None:
        return None, "missing"
    value = float(value)
    if math.isnan(value):
        return None, "nan"
    if math.isinf(value):
        return None, "+inf" if value > 0 else "-inf"
    return value, "finite"


def safe_json(value):
    if isinstance(value, dict):
        return {key: safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_json(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class EvaluationTrace:
    """Flush every callback and publish a trace only after result validation."""

    def __init__(self, output_path, run_key, timer=time.perf_counter):
        self.output_path = Path(output_path)
        self.run_key = dict(run_key)
        self.timer = timer
        self.events = []
        self.seen = set()
        self.completed = False

    def __enter__(self):
        if ACTIVE_TRACE.get() is not None:
            raise RuntimeError("Nested evaluation traces are not supported")
        directory = self.output_path.with_suffix(".traces")
        directory.mkdir(parents=True, exist_ok=True)
        key_hash = hashlib.sha256(
            json.dumps(self.run_key, sort_keys=True).encode()
        ).hexdigest()[:16]
        self.path = directory / f"{key_hash}_{uuid.uuid4().hex}.partial.jsonl"
        self.handle = self.path.open("x", encoding="utf-8")
        self.write({
            "event": "run_start", "trace_version": TRACE_VERSION,
            "run_key": self.run_key,
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "clock_origin": "runner entry, including setup and trace overhead",
            "point_mapping": "Python int(round(x)); same as lookup objectives",
            "evaluation_source": "lookup; no GDP/NLP solve is performed",
        })
        self.origin = self.timer()
        self.token = ACTIVE_TRACE.set(self)
        return self

    def write(self, event):
        self.handle.write(json.dumps(safe_json(event), allow_nan=False) + "\n")
        self.handle.flush()

    def record(self, point, value, incumbent, elapsed, started, finished,
               exception_type=None):
        requested = list(point)
        lattice = tuple(int(round(x)) for x in requested)
        raw_value, value_kind = finite_value(value)
        best, best_kind = finite_value(incumbent)
        event = {
            "event": "evaluation", "evaluation_index": len(self.events) + 1,
            "phase": ("initial" if len(self.events) < self.run_key["n_starts"]
                      else "adaptive"),
            "requested_point": requested, "point": list(lattice),
            "repeated_point": lattice in self.seen,
            "value": raw_value, "value_kind": value_kind,
            "incumbent": best, "incumbent_kind": best_kind,
            "objective_wall_s": elapsed,
            "started_elapsed_s": started - self.origin,
            "completed_elapsed_s": finished - self.origin,
            "exception_type": exception_type,
        }
        self.write(event)
        self.events.append(event)
        self.seen.add(lattice)

    def complete(self, record):
        validate_events(self.events, record)
        self.write({"event": "run_complete", "result_record": record,
                    "runner_elapsed_s": self.timer() - self.origin})
        self.handle.close()
        final_path = self.path.with_name(self.path.name.replace(".partial", ""))
        self.path.rename(final_path)
        self.path = final_path
        self.completed = True
        return {
            "path": self.path.relative_to(self.output_path.parent).as_posix(),
            "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
            "evaluations": len(self.events),
        }

    def __exit__(self, exc_type, exc, traceback):
        try:
            if not self.completed:
                self.write({"event": "run_incomplete",
                            "exception_type": exc_type.__name__ if exc_type else None})
        finally:
            self.handle.close()
            ACTIVE_TRACE.reset(self.token)


def validate_events(events, record):
    """Do not certify a trace unless callbacks match the saved result history."""
    if len(events) != int(record["total_evals"]):
        raise ValueError("Evaluation trace count does not match result total_evals")
    if any(event["exception_type"] for event in events):
        raise ValueError("Cannot complete an evaluation trace containing exceptions")
    if [event["evaluation_index"] for event in events] != list(range(1, len(events) + 1)):
        raise ValueError("Evaluation trace indices are not contiguous")
    trajectory = [event["incumbent"] for event in events]
    if trajectory != safe_json(record["incumbent_trajectory"]):
        raise ValueError("Evaluation trace does not match incumbent trajectory")
    if sum(event["phase"] == "initial" for event in events) != record["initial_evals"]:
        raise ValueError("Evaluation trace initial-call count does not match")


def validate_trace_artifacts(manifest, csv_path, records):
    """Validate sidecar checksums, run identities, and histories on resume/read."""
    if not manifest["protocol"].get("trace_evaluations"):
        return []
    artifacts = manifest.get("evaluation_traces", [])
    if len(artifacts) != len(records):
        raise ValueError("Checkpoint evaluation trace count does not match CSV rows")
    for artifact, key, record in zip(
        artifacts, manifest["run"]["completed_run_keys"], records
    ):
        path = Path(csv_path).parent / artifact["path"]
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
            raise ValueError(f"Evaluation trace checksum mismatch: {path.name}")
        entries = [json.loads(line) for line in data.splitlines()]
        if (entries[0].get("trace_version") != TRACE_VERSION
                or entries[0].get("run_key") != key
                or entries[-1].get("event") != "run_complete"):
            raise ValueError("Evaluation trace identity/completion mismatch")
        saved = dict(entries[-1]["result_record"])
        expected = safe_json(record)
        # CSV preserves status text, whereas a native solver may return an int.
        for item in (saved, expected):
            if item["solver_status"] is not None:
                item["solver_status"] = str(item["solver_status"])
        if saved != expected:
            raise ValueError("Evaluation trace result does not match CSV row")
        events = [event for event in entries if event["event"] == "evaluation"]
        validate_events(events, record)
        if artifact["evaluations"] != len(events):
            raise ValueError("Evaluation trace manifest count mismatch")
    return artifacts
