#!/usr/bin/env python3
"""Audit and summarize immutable PR56 returns. Never imports or runs an optimizer."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET
import zipfile

REVISION = "c4d7db6b671bbe92a314be524a650d75cd49529c"
ARCHIVE_SHA = "323e7c0bf27012c4838d6273630cf3d55b5ff64a6092802539bf7d63cc1f9c55"
SEALED_SHA = "e58982f7179b73c65d83134dcbe0b25854002685812b2511b24523e861c9929e"
GRID_COST_SHA = "2490d8f8de368d9b54d6cd3d9082ace5c74dfa2ebb84fd266b0488a43a7fcd0f"
CONTEXT_SHA = {
    "executed_source_manifest.json": "87ed05e9bae0141252c6d03f007042abb9b31cf990cd5e3212c24261fdd271af",
    "baseline_publication_manifest.json": "98c41bd3fe0cec9c0a1a54949e156e8b96995a722306faec996b1cccc6e9e811",
    "baseline_protocol.md": "19345b8c2aab36f22207555bff62a30eb999619fce126671d54e5d688d6e3954",
    "baseline_joint_runs.csv": "5c59364721a0676e5a27822afc9c034ec61eee66ff707a999fc617ab0880a2b0",
    "baseline_joint_manifest.json": "09ba1c9455761a5898f578dc7705b352458448f27a171c08a125db7a1f1f1c2f",
}
PRIMARY = (
    "dsda",
    "rbfopt_msrsm_genetic",
    "bam",
    "fmqa_sa",
    "uniform_without_replacement",
)
METHODS = PRIMARY + ("nomad", "miso")
LABELS = {
    "dsda": "D-SDA",
    "rbfopt_msrsm_genetic": "RBFOpt (genetic)",
    "bam": "BAM",
    "fmqa_sa": "FMQA-SA",
    "uniform_without_replacement": "Uniform",
    "nomad": "NOMAD",
    "miso": "MISO",
    "rbfopt_msrsm_solver": "RBFOpt solver control",
    "bam_predetermined_uniform": "BAM prefix control",
}
CASE_ORDER = (
    "cstr_5",
    "cstr_10",
    "cstr_15",
    "cstr_20",
    "cstr_25",
    "cstr_30",
    "column",
    "small_batch",
    "dynamic",
)
NUMERIC_THREADS = (
    "OMP_NUM_THREADS",
    "OMP_THREAD_LIMIT",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "GOTO_NUM_THREADS",
    "NUMEXPR_MAX_THREADS",
)
DEFAULT = Path(__file__).resolve().parents[1] / "results/pr56_dantzig_return_20261031"


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def close(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return (
            math.isfinite(a)
            and math.isfinite(b)
            and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
        )
    return a == b


def hit(value, target):
    return (
        value is not None
        and math.isfinite(value)
        and abs(value - target) <= 1e-5 * max(1, abs(target))
    )


def quantile(values, fraction):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    position = (len(values) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def exact_mcnemar(first_only, second_only):
    n = first_only + second_only
    return (
        1.0
        if not n
        else min(
            1.0,
            2
            * sum(math.comb(n, k) for k in range(min(first_only, second_only) + 1))
            / 2**n,
        )
    )


def holm(pvalues):
    result = [0.0] * len(pvalues)
    ceiling = 0.0
    for rank, index in enumerate(sorted(range(len(pvalues)), key=lambda i: pvalues[i])):
        ceiling = max(ceiling, min(1.0, (len(pvalues) - rank) * pvalues[index]))
        result[index] = ceiling
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def write_csv(path, rows):
    require(bool(rows), f"Empty output table: {path.name}")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def csv_bytes(data):
    return list(csv.DictReader(io.StringIO(data.decode())))


def key(spec):
    return spec["scope"], spec["case"], int(spec["budget"]), int(spec["seed"])


def points(events):
    return [event["point"] for event in events]


def duration(record):
    return (
        datetime.fromisoformat(record["finished_utc"])
        - datetime.fromisoformat(record["started_utc"])
    ).total_seconds()


class Evidence:
    def __init__(self, archive, context):
        self.archive = Path(archive)
        require(
            sha(self.archive.read_bytes()) == ARCHIVE_SHA,
            "Return archive SHA256 mismatch",
        )
        self.z = zipfile.ZipFile(self.archive)
        names = self.z.namelist()
        require(len(names) == len(set(names)), "Duplicate ZIP member names")
        require(
            all(
                not PurePosixPath(n).is_absolute()
                and ".." not in PurePosixPath(n).parts
                for n in names
            ),
            "Unsafe ZIP paths",
        )
        roots = {n.split("/")[0] for n in names}
        require(len(roots) == 1, "Ambiguous return root")
        self.root = next(iter(roots)) + "/"
        self.names = {n[len(self.root) :] for n in names}
        require(self.z.testzip() is None, "Return ZIP CRC failure")
        listing = self.data("SHA256SUMS").decode().splitlines()
        hashed = set()
        for line in listing:
            digest, name = line.split("  ", 1)
            require(
                name not in hashed and sha(self.data(name)) == digest,
                f"Internal SHA256 mismatch: {name}",
            )
            hashed.add(name)
        require(hashed == self.names - {"SHA256SUMS"}, "Uninventoried ZIP members")
        self.audit = dict(
            archive_sha256=ARCHIVE_SHA,
            zip_crc_passed=True,
            internal_members_verified=len(hashed),
            errors=[],
            no_optimizer_or_nlp_executed=True,
        )
        self.context = Path(context)
        for name, digest in CONTEXT_SHA.items():
            require(
                sha((self.context / name).read_bytes()) == digest,
                f"Pinned PR context changed: {name}",
            )
        self.source = json.loads(
            (self.context / "executed_source_manifest.json").read_text()
        )
        require(
            self.source["revision"] == REVISION, "Source manifest revision mismatch"
        )
        self.plan = self.json("plan.json")
        require(self.plan["revision"] == REVISION, "Execution revision mismatch")
        for name, digest in self.plan["hashes"].items():
            require(
                self.source["files"][name]
                == digest
                == sha(self.data("source_snapshot/" + name)),
                f"Executed source/input differs from PR56: {name}",
            )
        self.package = next(
            n.removesuffix("SHA256SUMS.json")
            for n in self.names
            if n.endswith("/reproduction/SHA256SUMS.json")
            and n.startswith("verified_inputs/")
        )
        sealed_hashes = self.json(self.package + "SHA256SUMS.json")
        embedded = self.data(
            "source_snapshot/results/archives/dsda_abs1e5_rerun_20261028_020753_2004611.zip"
        )
        require(sha(embedded) == SEALED_SHA, "Sealed archive hash mismatch")
        self.old_zip = zipfile.ZipFile(io.BytesIO(embedded))
        self.old_root = "dsda_abs1e5_rerun_20261028_020753_2004611/"
        for name, digest in sealed_hashes.items():
            payload = self.data(self.package + name)
            require(
                sha(payload) == digest
                and payload
                == self.old_zip.read(self.old_root + "reproduction/" + name),
                f"Sealed input mismatch: {name}",
            )
        self.audit["sealed_members_verified"] = len(sealed_hashes)
        self.jobs = {
            j["spec"]["job_id"].rsplit("_dsda", 1)[0]: j
            for j in self.json(self.package + "inputs/jobs.json")
        }
        require(len(self.jobs) == 1190, "Expected 1,190 independent job specifications")
        require(
            self.plan["jobs_sha256"]
            == sha(self.data(self.package + "inputs/jobs.json")),
            "Job hash mismatch",
        )
        self.canonical = {key(j["spec"]): j for j in self.jobs.values()}
        require(len(self.canonical) == 1190, "Duplicate condition/seed keys")
        self.cost_path = (
            "source_snapshot/results/grid_gdp_20261009/raw/point_timings.csv"
        )
        require(sha(self.data(self.cost_path)) == GRID_COST_SHA, "Grid costs changed")
        self.grid_costs = {
            (r["grid_name"], tuple(json.loads(r["point"]))): float(r["point_wall_s"])
            for r in self.csv(self.cost_path)
        }
        self.coverage_rows = self.csv(
            "source_snapshot/results/dsda_publication_20261028/tables/configuration_coverage.csv"
        )
        self.coverage = {
            (r["case"], tuple(json.loads(r["coordinates"]))): r["status"]
            for r in self.coverage_rows
        }
        self.process_visits = defaultdict(Counter)
        self.response_cache = {}
        self.primary = []
        self.dsda = []
        self.attempts = []
        self.bundles = []

    def data(self, name):
        return self.z.read(self.root + name)

    def json(self, name):
        return json.loads(self.data(name))

    def csv(self, name):
        return csv_bytes(self.data(name))

    def events(self, name):
        return [json.loads(line) for line in self.data(name).splitlines() if line]

    def responses(self, job):
        spec = job["spec"]
        cache_key = spec["scope"], spec["case"]
        if cache_key in self.response_cache:
            return self.response_cache[cache_key]
        response = {}
        if spec["scope"] == "grid":
            for row in self.csv(self.package + f"inputs/grids/{spec['case']}.csv"):
                point = tuple(json.loads(row["Point"]))
                response[point] = (
                    True,
                    float(row["z_norm"]),
                    self.grid_costs[spec["case"], point],
                    True,
                )
        else:
            for row in self.csv(
                self.package + f"inputs/process/{spec['case']}_full.csv"
            ):
                point = tuple(json.loads(row["point"]))
                accepted = row["accepted"] == "True"
                response[point] = (
                    accepted,
                    float(row["objective"]) if accepted else None,
                    float(row["total_wall_s"]),
                    self.coverage[spec["case"], point]
                    in ("accepted", "rejected", "solver_error"),
                )
        self.response_cache[cache_key] = response
        return response


def audit_events(job, events, responses, label, midfo):
    spec = job["spec"]
    require(3 <= len(events) <= spec["budget"], f"{label}: budget violation")
    require(
        points(events[:3]) == spec["starts"], f"{label}: shared initial order changed"
    )
    costs, nlp = [], []
    for index, event in enumerate(events, 1):
        point = tuple(event["point"])
        require(
            len(point) == len(spec["lower"])
            and all(
                isinstance(x, int) and lo <= x <= hi
                for x, lo, hi in zip(point, spec["lower"], spec["upper"])
            ),
            f"{label}: invalid integer coordinates",
        )
        require(
            point in responses and event["index"] == index,
            f"{label}: unknown response/index",
        )
        accepted, objective, cost, solved = responses[point]
        require(
            event["accepted"] == accepted
            and event["raw_objective"] == objective
            and event["method_value"] == (objective if accepted else 1e6),
            f"{label}: response/penalty changed",
        )
        require(
            event["lookup_wall_s"] >= 0 and not event.get("budget_overrun", False),
            f"{label}: invalid lookup time/overrun",
        )
        if midfo:
            require(
                event["point_cost_s"] == cost and event["nlp_solve"] == solved,
                f"{label}: point cost/NLP-equivalent count changed",
            )
            if index <= 3:
                require(
                    event["origin"] == "shared_start",
                    f"{label}: initial origin changed",
                )
        costs.append(cost)
        nlp.append(solved)
    return costs, nlp


def recompute(job, result, events, timing_events, costs, nlp, successful_status):
    accepted = [e for e in events if e["accepted"]]
    best = min(accepted, key=lambda e: e["raw_objective"]) if accepted else None
    reached = bool(
        successful_status and best and hit(best["raw_objective"], job["target"])
    )
    lookup = math.fsum(e["lookup_wall_s"] for e in timing_events)
    elapsed = result["search_s"]
    if elapsed is not None:
        require(
            math.isfinite(elapsed) and elapsed >= lookup,
            "Invalid measured search/lookup accounting",
        )
    prep = float(job["baseline"]["prep_s"])
    point_cost = math.fsum(costs)
    return dict(
        best_objective=best["raw_objective"] if best else None,
        best_point=best["point"] if best else None,
        evaluations=len(events),
        nlp_solves=sum(nlp),
        hit=reached,
        first_hit=next(
            (e["index"] for e in accepted if hit(e["raw_objective"], job["target"])),
            None,
        )
        if reached
        else None,
        category="execution_failed"
        if not successful_status or best is None
        else "target_reached"
        if reached
        else "target_not_reached",
        lookup_s=lookup,
        point_cost_s=point_cost,
        prep_s=prep,
        retained_search_s=elapsed - lookup if elapsed is not None else None,
        completion_s=elapsed - lookup + point_cost + prep
        if elapsed is not None
        else None,
    )


def audit_record(
    evidence, job, result, events, timing_events, label, cpu, midfo, successful_status
):
    responses = evidence.responses(job)
    costs, nlp = audit_events(job, events, responses, label, midfo)
    if timing_events is not events:
        audit_events(job, timing_events, responses, label + " selected rerun", midfo)
        require(
            points(events) == points(timing_events),
            f"{label}: accepted retry path differs",
        )
    require(
        result["target"] == job["target"] and result["process_nlp_calls"] == 0,
        f"{label}: target changed or new NLP calls",
    )
    require(result["effective_cpus"] == [cpu], f"{label}: incorrect CPU affinity")
    if midfo:
        require(
            result["overruns"] == 0
            and not result["invalid_points"]
            and result["penalty"] == 1e6,
            f"{label}: adapter/penalty violation",
        )
    else:
        require(
            result["improvement_abs_tol"] == 1e-5
            and result["unused_budget"] == job["spec"]["budget"] - len(events),
            f"{label}: D-SDA protocol changed",
        )
    metrics = recompute(
        job, result, events, timing_events, costs, nlp, successful_status
    )
    for field, value in metrics.items():
        if not midfo and field == "nlp_solves":
            continue
        require(
            close(result[field], value), f"{label}: recomputation mismatch: {field}"
        )
    return metrics


def normalized(job, result, metrics, method, member, timing_member, cohort):
    spec = job["spec"]
    return dict(
        scope=spec["scope"],
        case=spec["case"],
        budget=spec["budget"],
        seed=spec["seed"],
        method=method,
        cohort=cohort,
        status=result["status"],
        **metrics,
        search_s=result["search_s"],
        timing_observed=result["search_s"] is not None,
        source_member=member,
        timing_callbacks_member=timing_member,
    )


def audit_midfo(e):
    groups = e.plan["groups"]
    requested = [(g["method"], j) for g in groups for j in g["jobs"]]
    require(
        len(groups) == 66 and len(requested) == len(set(requested)) == 2380,
        "Job groups overlap or have wrong size",
    )
    require(
        set(requested) == {(m, j) for m in ("nomad", "miso") for j in e.jobs},
        "Job union differs from sealed plan",
    )
    campaign = e.json("campaign.json")
    cpu_map = {r["cpu"]: r for r in campaign["cpus"]}
    require(
        len(cpu_map) <= 6
        and len({(r["socket"], r["core"]) for r in cpu_map.values()}) == len(cpu_map),
        "SMT siblings shared between workers",
    )
    expected_members = set()
    for group in groups:
        base = f"batches/{group['name']}/"
        execution = e.json(base + "execution.json")
        selection = e.json(base + "selection.json")
        require(
            execution["exit_code"] == 0 and execution["state"] == "completed",
            f"Abnormal bundle: {group['name']}",
        )
        require(
            selection
            == dict(
                selected_attempt="attempt_01",
                method=group["method"],
                jobs=group["jobs"],
            ),
            "Bundle attempt selection changed",
        )
        command = execution["command"]
        require(
            command[command.index("--jobs") + 1 :] == group["jobs"]
            and command[command.index("--methods") + 1] == group["method"],
            "Bundle command/job list differs",
        )
        require(
            "--nomad-param" not in command
            and "--timeout" not in command
            and "--budgets" not in command,
            "Unexpected algorithm override",
        )
        cpu = execution["cpu"]
        require(
            cpu in cpu_map and int(command[command.index("--cpu") + 1]) == cpu,
            "Unknown bundle CPU",
        )
        manifest = e.json(base + "attempt_01/manifest.json")
        require(
            manifest["git_head"] == REVISION
            and manifest["git_status"] == ""
            and manifest["process_nlp_calls"] == 0,
            "Runtime source changed",
        )
        require(
            manifest["archive_sha256"] == SEALED_SHA
            and manifest["grid_costs_sha256"] == GRID_COST_SHA,
            "Runtime input hash changed",
        )
        require(
            manifest["script_sha256"]
            == e.plan["hashes"]["experiments/mixed_integer_dfo/run.py"],
            "Runner source changed",
        )
        require(
            manifest["cpu"]["effective_cpus"] == [cpu]
            and all(manifest["threads"][k] == "1" for k in NUMERIC_THREADS),
            "Runtime affinity/thread limit changed",
        )
        require(
            manifest["versions"]
            == dict(
                numpy="2.4.6",
                pandas="2.3.3",
                scipy="1.17.1",
                PyNomadBBO="4.6.0",
                soogo="2.1.0",
            )
            and manifest["python"] == "3.11.16",
            "Unexpected installed environment",
        )
        e.bundles.append(
            dict(
                name=group["name"],
                method=group["method"],
                jobs=len(group["jobs"]),
                cpu=cpu,
                socket=cpu_map[cpu]["socket"],
                core=cpu_map[cpu]["core"],
                pid=execution["pid"],
                started_utc=execution["started_utc"],
                finished_utc=execution["finished_utc"],
                elapsed_s=duration(execution),
                exit_code=execution["exit_code"],
            )
        )
        for jid in group["jobs"]:
            job = e.jobs[jid]
            folder = base + f"attempt_01/runs/{jid}__{group['method']}/"
            member = folder + "result.json"
            expected_members.add(member)
            result = e.json(member)
            require(
                result["spec"]
                == {
                    **job["spec"],
                    "method": group["method"],
                    "job_id": jid + "_" + group["method"],
                },
                f"{jid}: spec/seed/budget changed",
            )
            events = e.events(folder + "callbacks.jsonl")
            timing_events = events
            timing_member = folder + "callbacks.jsonl"
            history = result["solver"].get("reruns", [])
            if history:
                require(
                    group["method"] == "nomad"
                    and history[0]["status"].startswith("crashed")
                    and history[0]["extra"] == []
                    and history[0]["evaluations"] == len(events),
                    "Bad original crash history",
                )
                e.attempts.append(
                    dict(
                        job_id=jid,
                        method="nomad",
                        attempt=0,
                        status=history[0]["status"],
                        evaluations=len(events),
                        same_path=True,
                        selected=False,
                        result_member=None,
                        callbacks_member=folder + "callbacks.jsonl",
                        elapsed_s=None,
                    )
                )
                accepted_rerun = None
                for n, record in enumerate(history[1:], 1):
                    attempt_member = folder + f"rerun_{n}/result.json"
                    attempt = e.json(attempt_member)
                    attempt_events = e.events(folder + f"rerun_{n}/callbacks.jsonl")
                    require(
                        record["extra"] == [f"MAX_EVAL {5000 if n == 1 else 20000}"],
                        "NOMAD retry cap changed",
                    )
                    same = points(attempt_events) == points(events)
                    require(
                        record["status"] == attempt["status"]
                        and record["evaluations"] == len(attempt_events)
                        and record["same_path_as_crash"] == same,
                        "NOMAD retry history does not match files",
                    )
                    audit_record(
                        e,
                        job,
                        attempt,
                        attempt_events,
                        attempt_events,
                        attempt_member,
                        cpu,
                        True,
                        attempt["status"] == "completed",
                    )
                    if attempt["status"] == "completed" and same:
                        accepted_rerun = n
                    e.attempts.append(
                        dict(
                            job_id=jid,
                            method="nomad",
                            attempt=n,
                            status=attempt["status"],
                            evaluations=len(attempt_events),
                            same_path=same,
                            selected=attempt["status"] == "completed" and same,
                            result_member=attempt_member,
                            callbacks_member=folder + f"rerun_{n}/callbacks.jsonl",
                            elapsed_s=attempt["search_s"],
                        )
                    )
                if result["status"] == "completed_after_verified_rerun":
                    require(
                        accepted_rerun == len(history) - 1,
                        "Invalid accepted NOMAD retry",
                    )
                    timing_member = folder + f"rerun_{accepted_rerun}/callbacks.jsonl"
                    timing_events = e.events(timing_member)
                    require(
                        result["search_s"]
                        == e.json(folder + f"rerun_{accepted_rerun}/result.json")[
                            "search_s"
                        ],
                        "Wrong selected retry time",
                    )
                elif result["status"] == "crashed_identical_reruns":
                    require(
                        len(history) == 3
                        and all(h["status"].startswith("crashed") for h in history)
                        and all(h["same_path_as_crash"] for h in history[1:]),
                        "Repeated crash policy not satisfied",
                    )
                    require(
                        result["search_s"] is None
                        and result["completion_s"] is None
                        and result["retained_search_s"] is None,
                        "Missing crash time was imputed",
                    )
                else:
                    raise AuditError("Unexpected terminal retry state")
            else:
                require(
                    result["status"] == "completed",
                    "Unexpected non-retry terminal state",
                )
                e.attempts.append(
                    dict(
                        job_id=jid,
                        method=group["method"],
                        attempt=0,
                        status=result["status"],
                        evaluations=len(events),
                        same_path=True,
                        selected=True,
                        result_member=member,
                        callbacks_member=timing_member,
                        elapsed_s=result["search_s"],
                    )
                )
            if group["method"] == "miso":
                require(
                    result["solver"]["coordinate_perturbation"] == "integer_dds",
                    "MISO integer adapter changed",
                )
                design = [event for event in events if event["origin"] == "miso_design"]
                require(
                    result["solver"]["design_points"] == 3 + len(design),
                    "MISO design points were not charged",
                )
                if job["spec"]["case"] == "small_batch":
                    require(
                        len(design) >= 1 and len(events) <= job["spec"]["budget"],
                        "Small Batch initial design missing or uncharged",
                    )
            metrics = audit_record(
                e,
                job,
                result,
                events,
                timing_events,
                member,
                cpu,
                True,
                result["status"]
                in (
                    "completed",
                    "completed_after_verified_rerun",
                    "crashed_identical_reruns",
                ),
            )
            e.primary.append(
                normalized(
                    job,
                    result,
                    metrics,
                    group["method"],
                    member,
                    timing_member,
                    "dantzig_return_20261031",
                )
            )
            if job["spec"]["scope"] == "process":
                e.process_visits[group["method"]].update(
                    (job["spec"]["case"], tuple(event["point"])) for event in events
                )
    actual = {
        n
        for n in e.names
        if n.startswith("batches/")
        and "/attempt_01/runs/" in n
        and n.endswith("/result.json")
        and "/rerun_" not in n
    }
    require(actual == expected_members, "Missing/unexpected primary result files")
    native_reruns = {
        n
        for n in e.names
        if n.startswith("batches/") and "/rerun_" in n and n.endswith("/result.json")
    }
    require(
        native_reruns == {a["result_member"] for a in e.attempts if a["attempt"] > 0},
        "Unaccounted native retry result files",
    )
    for cpu in cpu_map:
        ordered = sorted(
            (b for b in e.bundles if b["cpu"] == cpu), key=lambda b: b["started_utc"]
        )
        require(
            all(
                a["finished_utc"] <= b["started_utc"]
                for a, b in zip(ordered, ordered[1:])
            ),
            "Overlapping bundles on a worker CPU",
        )
    e.audit.update(
        mi_results=len(e.primary),
        native_attempts=len(e.attempts),
        bundle_count=len(e.bundles),
        independent_physical_cores=list(cpu_map.values()),
        duplicate_jobs=0,
        missing_jobs=0,
        batch_exit_codes_all_zero=True,
        all_affinities_and_threads_verified=True,
    )


def audit_dsda(e):
    manifest = e.json("dsda/attempt_01/manifest.json")
    cpu = e.json("dsda/execution.json")["cpu"]
    require(
        manifest["git_head"] == REVISION
        and manifest["script_sha256"]
        == e.plan["hashes"]["experiments/dsda_process_multistart/run.py"],
        "D-SDA source mismatch",
    )
    require(
        all(manifest["threads"][k] == "1" for k in NUMERIC_THREADS),
        "D-SDA thread setting changed",
    )
    variants = ("single", "ranked", "ranked_random")
    changes, replay, expected = [], [], set()
    for jid, job in e.jobs.items():
        if job["spec"]["scope"] != "process":
            continue
        by_variant = {}
        for variant in variants:
            folder = f"dsda/attempt_01/runs/{job['spec']['job_id']}__{variant}/"
            result = e.json(folder + "result.json")
            events = e.events(folder + "callbacks.jsonl")
            require(
                result["spec"] == job["spec"] and result["variant"] == variant,
                "D-SDA seed/spec/variant changed",
            )
            metrics = audit_record(
                e,
                job,
                result,
                events,
                events,
                folder,
                cpu,
                False,
                result["status"] in ("completed", "budget_completed"),
            )
            row = normalized(
                job,
                result,
                metrics,
                "dsda_" + variant,
                folder + "result.json",
                folder + "callbacks.jsonl",
                "dantzig_restart_20261031",
            )
            row.update(
                variant=variant,
                unused_budget=result["unused_budget"],
                descents=len(result["descents"])
                if result["descents"] is not None
                else 1,
            )
            e.dsda.append(row)
            by_variant[variant] = (result, events)
            expected.add(folder + "result.json")
        single, events = by_variant["single"]
        original_base = e.old_root + "runs/" + job["spec"]["job_id"] + "/"
        original = json.loads(e.old_zip.read(original_base + "result.json"))
        original_events = [
            json.loads(line)
            for line in e.old_zip.read(original_base + "callbacks.jsonl").splitlines()
        ]
        checks = {
            field: single[field] == original[field]
            for field in (
                "best_objective",
                "evaluations",
                "hit",
                "first_hit",
                "category",
            )
        }
        checks["callback_points"] = points(events) == points(original_events)
        require(all(checks.values()), f"D-SDA archived replay mismatch: {jid}")
        replay.append(dict(job_id=jid, **checks))
        for variant in variants[1:]:
            other, other_events = by_variant[variant]
            require(
                points(other_events[: len(events)]) == points(events),
                f"D-SDA first-descent prefix mismatch: {jid}",
            )
            require(
                other["best_objective"] <= single["best_objective"],
                "Restart worsened incumbent",
            )
            if (other["hit"], other["best_objective"]) != (
                single["hit"],
                single["best_objective"],
            ):
                changes.append(
                    dict(
                        job_id=jid,
                        case=job["spec"]["case"],
                        budget=job["spec"]["budget"],
                        seed=job["spec"]["seed"],
                        variant=variant,
                        single_hit=single["hit"],
                        restart_hit=other["hit"],
                        single_objective=single["best_objective"],
                        restart_objective=other["best_objective"],
                        improvement=single["best_objective"] - other["best_objective"],
                        target=job["target"],
                    )
                )
    actual = {
        n
        for n in e.names
        if n.startswith("dsda/attempt_01/runs/") and n.endswith("/result.json")
    }
    require(
        actual == expected and len(actual) == 420 and len(replay) == 140,
        "D-SDA count mismatch",
    )
    e.audit.update(
        dsda_results=420,
        dsda_exact_replays=140,
        dsda_prefix_checks=280,
        dsda_recomputed_results=420,
    )
    return changes, replay


def historical(e):
    manifest = json.loads(
        (e.context / "baseline_publication_manifest.json").read_text()
    )
    name = "source_snapshot/results/dsda_publication_20261028/tables/run_records.csv"
    require(
        sha(e.data(name)) == manifest["outputs_sha256"]["tables/run_records.csv"],
        "Published baseline table changed",
    )
    joint_payload = (e.context / "baseline_joint_runs.csv").read_bytes()
    joint_manifest = json.loads(
        (e.context / "baseline_joint_manifest.json").read_text()
    )
    require(
        sha(joint_payload) == joint_manifest["output_sha256"]["joint_runs.csv"],
        "Historical NLP accounting changed",
    )
    nlp_rows = {
        ("process", r["case"], int(r["budget"]), int(r["seed"]), r["method"]): r
        for r in csv_bytes(joint_payload)
        if r["family"] == "DFO"
    }
    rows = []
    for old in e.csv(name):
        s = {**old, "budget": int(old["budget"]), "seed": int(old["seed"])}
        job = e.canonical.get(key(s))
        require(
            job is not None or old["method"] not in PRIMARY,
            "Historical primary condition differs from the current plan",
        )
        numeric = {
            field: float(old[field])
            if old[field] and math.isfinite(float(old[field]))
            else None
            for field in (
                "best_objective",
                "search_s",
                "point_cost_s",
                "prep_s",
                "total_s",
            )
        }
        reached = old["hit"] == "True"
        require(
            reached == (old["category"] == "target_reached"),
            "Historical hit/category mismatch",
        )
        if reached and job is not None:
            require(
                hit(numeric["best_objective"], job["target"]),
                "Historical target predicate differs",
            )
        nlp = nlp_rows.get((*key(s), old["method"]))
        if nlp:
            require(
                (nlp["target_reached"] == "True") == reached
                and close(float(nlp["completion_s"]), numeric["total_s"])
                and int(nlp["callbacks"]) == int(old["evaluations"]),
                "Historical NLP table joins a different run",
            )
        rows.append(
            dict(
                scope=s["scope"],
                case=s["case"],
                budget=s["budget"],
                seed=s["seed"],
                method=s["method"],
                cohort="published_dsda_adoption_20261028",
                status="historical_" + old["category"],
                category=old["category"],
                hit=reached,
                best_objective=numeric["best_objective"],
                best_point=None,
                evaluations=int(old["evaluations"]),
                nlp_solves=int(nlp["nlp_calls"]) if nlp else None,
                first_hit=int(old["first_hit"]) if old["first_hit"] else None,
                search_s=None,
                lookup_s=None,
                retained_search_s=numeric["search_s"],
                point_cost_s=numeric["point_cost_s"],
                prep_s=numeric["prep_s"],
                completion_s=numeric["total_s"],
                timing_observed=numeric["total_s"] is not None,
                source_member=old["record_source"],
                timing_callbacks_member=None,
            )
        )
    primary = [r for r in rows if r["method"] in PRIMARY]
    require(
        len(primary) == 5950 and len(nlp_rows) == 700,
        "Historical primary cohort count changed",
    )
    require(
        len({(*key(r), r["method"]) for r in rows}) == len(rows),
        "Historical duplicate keys",
    )
    return rows


def summarize_rows(rows, group_fields):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in group_fields)].append(row)
    output = []
    for group_key, records in sorted(groups.items()):
        row = dict(zip(group_fields, group_key))
        row.update(
            runs=len(records),
            hits=sum(r["hit"] for r in records),
            execution_failures=sum(
                r["category"] == "execution_failed" for r in records
            ),
            native_crash_terminal=sum(
                r["status"] == "crashed_identical_reruns" for r in records
            ),
            verified_reruns=sum(
                r["status"] == "completed_after_verified_rerun" for r in records
            ),
            timed_runs=sum(r["completion_s"] is not None for r in records),
            missing_times=sum(r["completion_s"] is None for r in records),
            callbacks=sum(r["evaluations"] for r in records),
            full_budget_runs=sum(r["evaluations"] == r["budget"] for r in records),
        )
        for field in (
            "evaluations",
            "nlp_solves",
            "retained_search_s",
            "point_cost_s",
            "completion_s",
        ):
            values = [r[field] for r in records]
            row.update(
                {
                    f"{field}_q25": quantile(values, 0.25),
                    f"{field}_median": quantile(values, 0.5),
                    f"{field}_q75": quantile(values, 0.75),
                    f"{field}_available": sum(v is not None for v in values),
                }
            )
        row["observed_search_sum_s"] = math.fsum(
            r["retained_search_s"]
            for r in records
            if r["retained_search_s"] is not None
        )
        row["charged_point_cost_sum_s"] = math.fsum(
            r["point_cost_s"] for r in records if r["point_cost_s"] is not None
        )
        output.append(row)
    return output


def paired_comparisons(rows):
    by_key = {(*key(r), r["method"]): r for r in rows if r["method"] in METHODS}
    conditions = sorted(
        {(r["case"], r["budget"]) for r in rows if r["scope"] == "process"},
        key=lambda k: (CASE_ORDER.index(k[0]), k[1]),
    )
    contrasts = [
        ("nomad", "dsda"),
        ("nomad", "rbfopt_msrsm_genetic"),
        ("miso", "dsda"),
        ("miso", "rbfopt_msrsm_genetic"),
        ("miso", "nomad"),
    ]
    summaries, pairs = [], []
    for first, second in contrasts:
        for case, budget in conditions:
            counts = Counter()
            ratios = []
            for seed in range(10):
                a, b = (
                    by_key[("process", case, budget, seed, method)]
                    for method in (first, second)
                )
                category = (
                    "both"
                    if a["hit"] and b["hit"]
                    else "first_only"
                    if a["hit"]
                    else "second_only"
                    if b["hit"]
                    else "neither"
                )
                counts[category] += 1
                ratio = (
                    a["completion_s"] / b["completion_s"]
                    if a["completion_s"] is not None
                    and b["completion_s"] is not None
                    and b["completion_s"] > 0
                    else None
                )
                if ratio is not None:
                    ratios.append(ratio)
                pairs.append(
                    dict(
                        scope="process",
                        case=case,
                        budget=budget,
                        seed=seed,
                        first=first,
                        second=second,
                        first_hit=a["hit"],
                        second_hit=b["hit"],
                        first_objective=a["best_objective"],
                        second_objective=b["best_objective"],
                        first_evaluations=a["evaluations"],
                        second_evaluations=b["evaluations"],
                        first_nlp_equivalent=a["nlp_solves"],
                        second_nlp_equivalent=b["nlp_solves"],
                        first_completion_s=a["completion_s"],
                        second_completion_s=b["completion_s"],
                        first_over_second_completion_ratio=ratio,
                    )
                )
            summaries.append(
                dict(
                    case=case,
                    budget=budget,
                    first=first,
                    second=second,
                    pairs=10,
                    **{
                        k: counts[k]
                        for k in ("both", "first_only", "second_only", "neither")
                    },
                    p_exact=exact_mcnemar(counts["first_only"], counts["second_only"]),
                    timed_pairs=len(ratios),
                    median_paired_completion_ratio=quantile(ratios, 0.5),
                )
            )
    for row, adjusted in zip(summaries, holm([r["p_exact"] for r in summaries])):
        row.update(
            p_holm_70=adjusted,
            inference="exploratory; 70 contrasts; repeated Dynamic budgets are not independent replications",
        )
    return summaries, pairs


def reconcile_server(e):
    raw = {(*key(r), r["method"]): r for r in e.primary}
    returned = e.csv("aggregate/runs.csv")
    require(len(returned) == len(raw) == 2380, "Aggregate row count changed")
    fields = {
        "hit": "hit",
        "best_objective": "best_objective",
        "evaluations": "evaluations",
        "nlp_solves": "nlp_solves",
        "first_hit": "first_hit",
        "retained_search_s": "retained_search_s",
        "point_cost_s": "point_cost_s",
        "prep_s": "prep_s",
        "completion_s": "completion_s",
    }
    for row in returned:
        original = raw[
            (
                row["scope"],
                row["case"],
                int(row["budget"]),
                int(row["seed"]),
                row["method"],
            )
        ]
        require(row["status"] == original["status"], "Aggregate status changed")
        for field, source in fields.items():
            value = (
                row[field] == "True"
                if field == "hit"
                else float(row[field])
                if row[field]
                else None
            )
            require(
                close(value, original[source]), f"Server aggregate mismatch: {field}"
            )
    grouped = [
        {**r, "condition": r["case"] if r["scope"] == "process" else "all_grid"}
        for r in e.primary
    ]
    summaries = summarize_rows(grouped, ("scope", "condition", "budget", "method"))
    summary_keys = {
        (r["scope"], r["condition"], r["budget"], r["method"]): r for r in summaries
    }
    for row in e.csv("aggregate/condition_summary.csv"):
        r = summary_keys[(row["scope"], row["case"], int(row["budget"]), row["method"])]
        mapping = {
            "runs": "runs",
            "hits": "hits",
            "failures": "execution_failures",
            "verified_reruns": "verified_reruns",
            "median_evaluations": "evaluations_median",
            "median_nlp_solves": "nlp_solves_median",
            "median_search_s": "retained_search_s_median",
            "median_completion_s": "completion_s_median",
            "q25_completion_s": "completion_s_q25",
            "q75_completion_s": "completion_s_q75",
        }
        for field, source in mapping.items():
            require(
                close(float(row[field]), r[source]), f"Server summary mismatch: {field}"
            )
    e.audit.update(
        server_aggregate_rows_recomputed=2380,
        server_condition_summaries_recomputed=len(summaries),
    )


def analyze(archive, context):
    e = Evidence(archive, context)
    audit_midfo(e)
    changes, replay = audit_dsda(e)
    old = historical(e)
    coverage = []
    for record in e.coverage_rows:
        coordinate_key = (record["case"], tuple(json.loads(record["coordinates"])))
        prior = int(record["primary_callbacks"])
        nomad = e.process_visits["nomad"][coordinate_key]
        miso = e.process_visits["miso"][coordinate_key]
        coverage.append(
            dict(
                case=record["case"],
                coordinates=record["coordinates"],
                accepted=record["accepted"],
                status=record["status"],
                historical_primary_callbacks=prior,
                nomad_callbacks=nomad,
                miso_callbacks=miso,
                combined_primary_callbacks=prior + nomad + miso,
            )
        )
    require(
        all(set(visits) <= set(e.coverage) for visits in e.process_visits.values()),
        "A visited configuration is missing from the sealed response inventory",
    )
    combined_process = dict(
        runs=980,
        historical_callbacks=sum(r["historical_primary_callbacks"] for r in coverage),
        historical_distinct_configurations=sum(
            r["historical_primary_callbacks"] > 0 for r in coverage
        ),
        nomad_callbacks=sum(r["nomad_callbacks"] for r in coverage),
        miso_callbacks=sum(r["miso_callbacks"] for r in coverage),
        combined_callbacks=sum(r["combined_primary_callbacks"] for r in coverage),
        combined_distinct_configurations=sum(
            r["combined_primary_callbacks"] > 0 for r in coverage
        ),
        sealed_configuration_inventory=len(coverage),
        repeated_native_attempts_and_restart_diagnostics_excluded=True,
    )
    require(
        combined_process["historical_callbacks"] == 16041
        and combined_process["historical_distinct_configurations"] == 2024
        and combined_process["nomad_callbacks"] + combined_process["miso_callbacks"]
        == sum(r["evaluations"] for r in e.primary if r["scope"] == "process"),
        "Combined process callback accounting disagrees with primary records",
    )
    reconcile_server(e)
    server_validation = e.json("aggregate/validation.json")
    require(
        server_validation["validation_passed"]
        and not any(
            server_validation[k]
            for k in ("missing", "duplicates", "validation_errors", "abnormal_bundles")
        ),
        "Server reported unresolved validation issues",
    )
    preflight = e.json("preflight/validation.json")
    junit = ET.fromstring(e.data("preflight/junit.xml"))
    tests = list(junit.iter("testcase"))
    require(
        preflight["passed"] and len(tests) == 12 and all(not list(t) for t in tests),
        "Preflight has skipped/failed tests",
    )
    e.audit.update(
        preflight_passed=12,
        preflight_skipped=0,
        target_rule="abs(value-target) <= 1e-5 * max(1,abs(target))",
        original_failure_and_retry_policy_preserved=True,
        missing_times_not_imputed=True,
        server_validation_passed=True,
        validation_passed=True,
    )
    all_primary = [r for r in old if r["method"] in PRIMARY] + e.primary
    process = summarize_rows(
        [r for r in all_primary if r["scope"] == "process"],
        ("case", "budget", "method"),
    )
    grid = summarize_rows(
        [r for r in all_primary if r["scope"] == "grid"], ("budget", "method")
    )
    overall = summarize_rows(all_primary, ("scope", "method"))
    dsda_summary = summarize_rows(e.dsda, ("method",))
    dsda_condition = summarize_rows(e.dsda, ("case", "budget", "method"))
    paired, pairs = paired_comparisons(all_primary)
    crashes = [r for r in e.primary if r["status"] == "crashed_identical_reruns"]
    crash_sensitivity = []
    for scope in ("grid", "process"):
        rows = [r for r in e.primary if r["method"] == "nomad" and r["scope"] == scope]
        crash_sensitivity.append(
            dict(
                scope=scope,
                runs=len(rows),
                native_terminal_crashes=sum(
                    r["status"] == "crashed_identical_reruns" for r in rows
                ),
                adopted_path_scored_hits=sum(r["hit"] for r in rows),
                terminal_crash_as_failure_hits=sum(
                    r["hit"] and r["status"] != "crashed_identical_reruns" for r in rows
                ),
                all_initial_crash_as_failure_hits=sum(
                    r["hit"] and r["status"] == "completed" for r in rows
                ),
                missing_times=sum(r["completion_s"] is None for r in rows),
            )
        )
    campaign = e.json("campaign.json")
    start = e.json("deployment_snapshot/bootstrap.json")
    methods = {}
    for method in ("nomad", "miso"):
        rows = [r for r in e.primary if r["method"] == method]
        attempts = [a for a in e.attempts if a["method"] == method]
        methods[method] = dict(
            runs=len(rows),
            hits=sum(r["hit"] for r in rows),
            statuses=dict(Counter(r["status"] for r in rows)),
            execution_failures=sum(r["category"] == "execution_failed" for r in rows),
            native_attempts=len(attempts),
            native_crash_attempts=sum(
                a["status"].startswith("crashed") for a in attempts
            ),
            missing_times=sum(r["completion_s"] is None for r in rows),
            observed_selected_search_sum_s=math.fsum(
                r["retained_search_s"]
                for r in rows
                if r["retained_search_s"] is not None
            ),
            batch_wall_sum_s=math.fsum(
                b["elapsed_s"] for b in e.bundles if b["method"] == method
            ),
        )
    summary = dict(
        revision=REVISION,
        archive_sha256=ARCHIVE_SHA,
        planned_results=2800,
        dsda=dict(
            runs=420,
            replay_matched=140,
            variant_summaries=dsda_summary,
            changed_variant_comparisons=len(changes),
            changed_unique_jobs=len({r["job_id"] for r in changes}),
            changed_hits=sum(r["single_hit"] != r["restart_hit"] for r in changes),
        ),
        methods=methods,
        overall_comparison=overall,
        crash_sensitivity=crash_sensitivity,
        combined_primary_process=combined_process,
        execution=dict(
            started_utc=start["created_utc"],
            campaign_started_utc=campaign["started_utc"],
            experiments_finished_utc=campaign["finished_utc"],
            collected_utc=campaign["collected_utc"],
            launch_to_collection_s=(
                datetime.fromisoformat(campaign["collected_utc"])
                - datetime.fromisoformat(start["created_utc"])
            ).total_seconds(),
            cpu_mapping=campaign["cpus"],
            exclusive_reservation=False,
        ),
        environment=e.json("environment_actual.json"),
        analysis_has_no_new_optimization=True,
    )
    tables = dict(
        individual_new_runs=e.primary,
        historical_primary_runs=[r for r in old if r["method"] in PRIMARY],
        historical_control_runs=[r for r in old if r["method"] not in PRIMARY],
        dsda_runs=e.dsda,
        dsda_conditions=dsda_condition,
        dsda_changes=changes,
        dsda_replay=replay,
        process_conditions=process,
        grid_budgets=grid,
        grid_functions=summarize_rows(
            [r for r in all_primary if r["scope"] == "grid"],
            ("case", "budget", "method"),
        ),
        overall_comparison=overall,
        process_pairs=pairs,
        process_paired_tests=paired,
        nomad_terminal_crashes=crashes,
        nomad_crash_sensitivity=crash_sensitivity,
        native_attempts=e.attempts,
        execution_bundles=e.bundles,
        combined_configuration_coverage=coverage,
    )
    e.z.close()
    e.old_zip.close()
    return summary, e.audit, tables


def run(archive, context, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summary, validation, tables = analyze(archive, context)
    write_json(output / "summary.json", summary)
    write_json(output / "validation.json", validation)
    for name, rows in tables.items():
        write_csv(output / (name + ".csv"), rows)
    write_json(
        output / "REPRODUCTION.json",
        dict(
            source_revision=REVISION,
            input_sha256={"RETURN.zip": ARCHIVE_SHA, **CONTEXT_SHA},
            analyzer_sha256=sha(Path(__file__).read_bytes()),
            data_only=True,
            source_and_raw_results_modified=False,
            outputs_sha256={
                p.name: sha(p.read_bytes())
                for p in sorted(output.iterdir())
                if p.is_file() and p.name != "REPRODUCTION.json"
            },
        ),
    )
    print(
        json.dumps(
            dict(
                validation_passed=validation["validation_passed"],
                dsda=summary["dsda"]["runs"],
                nomad=summary["methods"]["nomad"]["runs"],
                miso=summary["methods"]["miso"]["runs"],
                output=str(output),
            ),
            indent=2,
        )
    )
    return summary, validation, tables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT / "evidence/RETURN.zip")
    parser.add_argument("--context", type=Path, default=DEFAULT / "evidence")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.archive, args.context, args.output)


if __name__ == "__main__":
    main()
