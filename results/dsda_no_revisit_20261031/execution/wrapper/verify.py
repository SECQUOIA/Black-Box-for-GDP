"""Data-only checks for the two unchanged Dantzig launchers."""

import csv
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import zipfile
from collections import Counter, defaultdict


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rows(path):
    with Path(path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def events(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def zip_check(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate ZIP members")
        require(
            all(not n.startswith("/") and ".." not in Path(n).parts for n in names),
            "Unsafe ZIP member",
        )
        require(archive.testzip() is None, "ZIP CRC failure")
    return dict(
        name=Path(path).name,
        bytes=Path(path).stat().st_size,
        sha256=sha(path),
        crc_passed=True,
    )


def audit_a(output, revision, expected_jobs=None):
    output = Path(output)
    manifest = read(output / "manifest.json")
    checks = read(output / "checks.json")
    check_rows = rows(output / "checks.csv")
    records = [read(p) for p in sorted((output / "runs").glob("*/result.json"))]
    require(manifest["git_head"] == revision, "A execution revision differs")
    require(manifest["process_nlp_calls"] == 0, "A reports live NLP calls")
    require(
        checks["passed"] and checks["jobs"] == 1470 and not checks["failures"],
        "A checks.json failed",
    )
    require(
        len(records) == len(check_rows) == 1470,
        "A result/check count differs from 1470",
    )
    by_key = {(r["spec"]["job_id"], r["variant"]): r for r in records}
    require(len(by_key) == 1470, "A duplicate result keys")
    if expected_jobs is not None:
        expected = {
            (j["spec"]["job_id"], v): j["spec"]
            for j in expected_jobs
            for v in (
                ["grid"]
                if j["spec"]["scope"] == "grid"
                else ["single", "ranked", "ranked_random"]
            )
        }
        require(
            set(expected) == set(by_key)
            and all(r["spec"] == expected[k] for k, r in by_key.items()),
            "A jobs/specs differ from the sealed input plan",
        )
    require(
        Counter(r["variant"] for r in records)
        == dict(grid=1050, single=140, ranked=140, ranked_random=140),
        "A variant counts differ",
    )
    checks_by_key = {(r["job_id"], r["variant"]): r for r in check_rows}
    require(
        set(checks_by_key) == set(by_key), "A checks do not cover exactly the results"
    )
    counts = Counter()
    historical = Counter()
    for key, record in by_key.items():
        spec = record["spec"]
        directory = output / "runs" / (spec["job_id"] + "__" + record["variant"])
        callbacks = events(directory / "callbacks.jsonl")
        points = [tuple(e["point"]) for e in callbacks]
        require(
            len(points) == len(set(points)) == record["evaluations"] <= spec["budget"],
            f"A repeats/budget mismatch: {key}",
        )
        require(
            [list(p) for p in points[: len(spec["starts"])]] == spec["starts"],
            f"A start order differs: {key}",
        )
        require(
            record["process_nlp_calls"] == 0 and not record["reevaluate_explored"],
            f"A wrong mode: {key}",
        )
        require(
            record["status"] in ("completed", "budget_completed")
            and not record["error"],
            f"A failed record: {key}",
        )
        require(
            all(
                len(p) == len(spec["lower"])
                and all(
                    isinstance(x, int) and lo <= x <= hi
                    for x, lo, hi in zip(p, spec["lower"], spec["upper"])
                )
                for p in points
            ),
            f"A invalid coordinates: {key}",
        )
        best = min(
            (e["raw_objective"] for e in callbacks if e["accepted"]), default=None
        )
        hit = best is not None and abs(best - record["target"]) <= 1e-5 * max(
            1, abs(record["target"])
        )
        require(
            best == record["best_objective"] and hit == record["hit"],
            f"A objective/hit mismatch: {key}",
        )
        require(spec["seed"] in range(10), f"A unexpected seed: {key}")
        check = checks_by_key[key]
        required = ["passed", "ok", "no_repeats"]
        required += (
            [
                "legacy_reproduces_published",
                "published_distinct_prefix",
                "not_worse",
                "hit_kept",
            ]
            if record["variant"] in ("grid", "single")
            else ["first_descent_matches_single"]
        )
        require(
            all(check[k] == "True" for k in required), f"A required check failed: {key}"
        )
        group = (
            f"grid_B{spec['budget']}"
            if record["variant"] == "grid"
            else record["variant"]
        )
        counts[group] += int(hit)
        if record["variant"] in ("grid", "single"):
            historical[group] += check["published_hit"] == "True"
        if record["variant"] in ("ranked", "ranked_random"):
            single = events(
                output / "runs" / (spec["job_id"] + "__single") / "callbacks.jsonl"
            )
            require(
                points[: len(single)] == [tuple(e["point"]) for e in single],
                f"A single prefix mismatch: {key}",
            )
    expected = dict(
        grid_B10=13,
        grid_B30=78,
        grid_B50=91,
        grid_B70=101,
        grid_B100=101,
        single=79,
        ranked=80,
        ranked_random=80,
    )
    require(
        dict(counts) == expected,
        f"A differs from supplied cross-check counts: {dict(counts)}",
    )
    require(len(rows(output / "runs.csv")) == 1470, "A runs.csv count differs")
    require(
        len(
            {
                (r["scope"], r["case"], r["budget"], r["seed"], r["variant"])
                for r in rows(output / "runs.csv")
            }
        )
        == 1470,
        "A duplicate summary rows",
    )
    return dict(
        passed=True,
        planned=1470,
        results=1470,
        missing=0,
        duplicates=0,
        hits=dict(counts),
        published_hits=dict(historical),
        historical_replays_passed=1190,
        first_descent_checks_passed=280,
        new_nlp_calls=0,
    )


def audit_b(output):
    """Preserve execution failures; structural accounting failures block publication."""
    output = Path(output)
    plan = read(output / "plan.json")
    jobs = {j["job_id"]: j for j in plan["jobs"]}
    methods = {"dsda", "rbfopt", "bam", "fmqa_sa", "uniform", "nomad", "miso"}
    expected = {
        f"{m}_B{b}_seed{s}" for m in methods for b in (25, 50, 100) for s in range(10)
    }
    require(
        len(plan["jobs"]) == 210 and set(jobs) == expected,
        "B plan is not the fixed 210-job set",
    )
    actual = {p.parent.name: p for p in (output / "runs").glob("*/result.json")}
    failures = {
        p.parent.name: read(p) for p in (output / "runs").glob("*/worker_failure.json")
    }
    require(set(actual) <= expected and set(failures) <= expected, "B unknown jobs")
    require(
        not (set(actual) & set(failures)),
        "B result/worker_failure conflict requires review",
    )
    missing = sorted(expected - set(actual) - set(failures))
    require(not missing, f"B jobs lack terminal records: {missing}")
    statuses = Counter()
    callback_count = 0
    recorded_solves = 0
    unknown_solves = []
    for jid, path in actual.items():
        r = read(path)
        require(r["spec"] == jobs[jid], f"B spec changed: {jid}")
        e = events(path.parent / "callbacks.jsonl")
        require(
            len(e) == r["evaluations"] <= jobs[jid]["budget"],
            f"B evaluation/budget mismatch: {jid}",
        )
        points = [tuple(x["point"]) for x in e]
        require(
            all(
                len(p) == 6 and all(isinstance(v, int) and 0 <= v <= 6 for v in p)
                for p in points
            ),
            f"B invalid coordinate: {jid}",
        )
        require(
            [list(p) for p in points[:7]] == jobs[jid]["starts"][: len(points[:7])],
            f"B initial order differs: {jid}",
        )
        if r["status"].startswith("completed"):
            require(len(e) >= 7, f"B completed without starts: {jid}")
        if jobs[jid]["method"] == "dsda":
            require(len(points) == len(set(points)), f"B D-SDA repeated a point: {jid}")
        best = min((x["raw_objective"] for x in e if x["accepted"]), default=None)
        require(best == r["best_objective"], f"B objective differs: {jid}")
        require(len(r["cpu"]) == 1, f"B worker not pinned: {jid}")
        statuses[r["status"]] += 1
        callback_count += len(e)
        if r.get("solved_now") is None:
            unknown_solves.append(jid)
        else:
            recorded_solves += r["solved_now"]
        # Prior failed native attempts may have solved points that the final result omits.
        if len(r.get("details", {}).get("attempts", [])) > 1:
            unknown_solves.append(jid + ":prior_native_attempt")
    connection = sqlite3.connect(f"file:{output / 'cache.sqlite'}?mode=ro", uri=True)
    cached = connection.execute("select gaps, record from responses").fetchall()
    provenance = connection.execute(
        "select value from meta where key='provenance'"
    ).fetchone()
    require(provenance is not None, "B cache has no provenance")
    connection.close()
    for gaps, record in cached:
        p, r = json.loads(gaps), json.loads(record)
        require(
            len(p) == 6 and all(0 <= v <= 6 for v in p) and sum(p) <= 17,
            "B invalid cached point",
        )
        if r["accepted"]:
            require(
                r["solver_row"]["solvestat"] == 1
                and r["solver_row"]["modelstat"] in (1, 2),
                "B accepted without CONOPT normal optimum",
            )
    return dict(
        passed=True,
        planned=210,
        result_files=len(actual),
        missing=0,
        duplicates=0,
        completed=sum(v for k, v in statuses.items() if k.startswith("completed")),
        result_failures=sum(
            v for k, v in statuses.items() if not k.startswith("completed")
        ),
        worker_failures=len(failures),
        worker_timeouts=sum(bool(r["timed_out"]) for r in failures.values()),
        statuses=dict(statuses),
        worker_failure_records=failures,
        callback_evaluations=callback_count,
        unique_cached_configurations=len(cached),
        accepted_cached_configurations=sum(
            json.loads(r)["accepted"] for _, r in cached
        ),
        recorded_nlp_calls=recorded_solves,
        nlp_call_count_exact=False,
        uncounted_attempts=unknown_solves,
        cache_provenance=json.loads(provenance[0]),
        cache_note="Unique cache rows and recorded solved_now counters are not an exact total NLP-call count: concurrent cache misses can solve the same point before INSERT OR IGNORE, and non-forked workers may report that race as cached; prior native attempts can also be uncounted. The existing cache and recording code are unchanged.",
    )


def audit_b_summary(output, audit):
    output = Path(output)
    table = rows(output / "runs.csv")
    require(
        len(table) == audit["result_files"]
        and len({r["job_id"] for r in table}) == len(table),
        "B summary coverage mismatch",
    )
    best = read(output / "best_known.json")
    require(math.isfinite(best["objective"]), "B best-known value is not finite")
    groups = defaultdict(lambda: dict(results=0, hits=0, completed=0))
    for job in read(output / "plan.json")["jobs"]:
        groups[job["method"], job["budget"]]
    for row in table:
        r = read(output / "runs" / row["job_id"] / "result.json")
        hit = r["best_objective"] is not None and abs(
            r["best_objective"] - best["objective"]
        ) <= 1e-5 * max(1, abs(best["objective"]))
        require((row["hit"] == "True") == hit, "B summary hit differs")
        g = groups[row["method"], int(row["budget"])]
        g["results"] += 1
        g["hits"] += hit
        g["completed"] += r["status"].startswith("completed")
    for row in rows(output / "conditions.csv"):
        g = groups[row["method"], int(row["budget"])]
        require(
            int(row["runs"]) == g["results"]
            and int(row["hits"]) == g["hits"]
            and int(row["completed"]) == g["completed"],
            "B condition summary differs",
        )
    audit["conditions"] = [
        dict(method=m, budget=b, planned=10, **g)
        for (m, b), g in sorted(groups.items())
    ]
    audit["best_known"] = best
    return audit
