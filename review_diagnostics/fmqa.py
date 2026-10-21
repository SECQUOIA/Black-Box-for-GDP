"""At most nine isolated historical-prefix fits and exhaustive binary energies."""

import argparse
import importlib
import itertools
import math
from pathlib import Path
import sys
import tempfile
import time
import types
from unittest.mock import patch
import warnings
import zipfile

from review_comparison.common import writecsv
from .common import ROOT, bounded, environment, outputs, save, sha
from .prepare import records

ATOL = 1e-6
RTOL = 1e-5
SAMPLE_ATOL = 1e-5


def load_historical(case, temporary):
    archive = ROOT / case["archive"]
    if sha(archive) != case["archive_sha256"]:
        raise ValueError("Historical archive hash changed")
    package = temporary / case["case"]
    with zipfile.ZipFile(archive) as z:
        for relative, expected in case["source_files_sha256"].items():
            path = package / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(z.read(case["source_prefix"] + relative))
            if sha(path) != expected:
                raise ValueError("Archived source mismatch: " + relative)
    name = "_diagnostic_" + case["case"]
    module = types.ModuleType(name)
    module.__path__ = [str(package / "fmqa_benchmark")]
    sys.modules[name] = module
    return importlib.import_module(name + ".qhd_surrogate"), importlib.import_module(
        name + ".optimizer"
    )


def classify(encoding, bits, seen):
    point = encoding.decode(bits)
    valid = encoding.valid(point)
    already = point in seen
    return point, valid, already, valid and not already


def check_close(a, b, atol=ATOL, rtol=RTOL):
    return (
        math.isfinite(a)
        and math.isfinite(b)
        and abs(a - b) <= atol + rtol * max(abs(a), abs(b))
    )


def exhaustive(model, encoding, seen):
    import numpy as np
    import torch

    if encoding.n_bits > 10:
        raise ValueError(
            f"Bit count {encoding.n_bits} exceeds the authorized ten-bit domain"
        )
    bias, linear, interaction = model.fm.get_bhQ()
    Q = interaction.copy()
    np.fill_diagonal(Q, linear)
    scale = float(np.max(np.abs(Q)))
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError(
            "Zero/nonfinite scale requires the separate synthetic diagnostic"
        )
    raw_qubo, raw_bias = model._fm_to_qubo(scaling=False)
    strings = [
        "".join(bits) for bits in itertools.product("01", repeat=encoding.n_bits)
    ]
    matrix = np.array([[int(b) for b in s] for s in strings])
    with torch.no_grad():
        predictions = (
            model.fm(torch.tensor(matrix, dtype=torch.float32))
            .cpu()
            .numpy()
            .reshape(-1)
        )
    h = model.fm.h.detach().cpu().numpy().astype(float)
    v = model.fm.V.detach().cpu().numpy().astype(float)
    rows = []
    for bits, x, prediction in zip(strings, matrix, predictions):
        # Independent float64 FM formula includes each i<j interaction exactly once.
        direct = float(
            bias
            + np.dot(h, x)
            + sum(
                float(np.dot(v[:, i], v[:, j])) * x[i] * x[j]
                for i in range(len(x))
                for j in range(i + 1, len(x))
            )
        )
        raw = float(
            raw_bias + sum(float(q) * x[i] * x[j] for (i, j), q in raw_qubo.items())
        )
        scaled = float(model.energy(dict(enumerate(x))))
        restored = scaled * scale
        point, valid, already, eligible = classify(encoding, bits, seen)
        errors = [abs(direct - raw), abs(float(prediction) - raw), abs(restored - raw)]
        rows.append(
            {
                "bits": bits,
                "point": list(point),
                "fm_prediction_float32": float(prediction),
                "fm_formula_float64": direct,
                "unscaled_qubo_with_bias": raw,
                "bqm_scaled_energy_with_offset": scaled,
                "restored_bqm_energy": restored,
                "scaling_factor": scale,
                "valid_domain": valid,
                "already_evaluated": already,
                "eligible": eligible,
                "classification": "out_of_bounds"
                if not valid
                else "already_evaluated"
                if already
                else "eligible",
                "maximum_absolute_identity_error": max(errors),
                "maximum_relative_identity_error": max(errors) / max(abs(raw), ATOL),
                "identity_pass": all(
                    check_close(value, raw)
                    for value in (direct, float(prediction), restored)
                ),
            }
        )
    return rows, {
        "bias": bias,
        "linear": h.tolist(),
        "V": v.tolist(),
        "unscaled_Q": Q.tolist(),
        "scaled_linear": dict(model.linear),
        "scaled_quadratic": [
            [int(i), int(j), float(q)] for (i, j), q in model.quadratic.items()
        ],
        "scaled_offset": float(model.offset),
        "scaling_factor": scale,
    }


def synthetic(qhd):
    """No fitting: construct exact constant FMs and observe the actual converter/guard."""
    import torch

    qhd.cpu_settings()
    upstream, _ = qhd.upstream()
    results = []
    for bias in (0.0, 3.0):
        model = upstream.FMBQM(2, "BINARY")
        with torch.no_grad():
            model.fm.h.zero_()
            model.fm.V.zero_()
            model.fm.bias.fill_(bias)
        raw, raw_bias = model._fm_to_qubo(scaling=False)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            Q, b = model._fm_to_qubo()
        model.offset = b
        for i in range(2):
            model.linear[i] = Q[i, i]
            for j in range(i + 1, 2):
                model.quadratic[i, j] = Q.get((i, j), 0.0)
        raised = None
        with patch.object(
            qhd, "upstream", return_value=(upstream, lambda *a, **k: model)
        ):
            try:
                qhd.train(
                    ["00", "01"], [bias, bias], seed=0, epochs=1, learning_rate=0.01
                )
            except Exception as error:
                raised = f"{type(error).__name__}: {error}"
        results.append(
            {
                "kind": "synthetic constant FM; manually assigned weights; no fit",
                "bias": bias,
                "Q_all_zero_before_scaling": all(float(v) == 0 for v in raw.values()),
                "unscaled_energy": raw_bias,
                "scaling_factor": 0.0,
                "scaled_coefficients": {str(k): repr(float(v)) for k, v in Q.items()},
                "scaled_offset": repr(float(b)),
                "warnings": [str(w.message) for w in caught],
                "historical_wrapper_guard_exception": raised,
                "uniform_fallback_invoked": False,
                "training_calls": 0,
                "sa_calls": 0,
            }
        )
    # Nonzero control tests interaction, nonzero bias and coefficient normalization.
    control = upstream.FMBQM(2, "BINARY")
    with torch.no_grad():
        control.fm.h.copy_(torch.tensor([2.0, -1.0]))
        control.fm.bias.fill_(3.0)
        control.fm.V.fill_(0.0)
        control.fm.V[0].copy_(torch.tensor([1.0, 2.0]))
    Q, b = control._fm_to_qubo()
    control.offset = b
    control.linear[0], control.linear[1] = Q[0, 0], Q[1, 1]
    control.quadratic[0, 1] = Q[0, 1]
    from fmqa_benchmark.optimizer import BinaryCoordinates

    rows, weights = exhaustive(control, BinaryCoordinates([0, 0], [1, 1]), {(0, 0)})
    return {
        "zero_scale_cases": results,
        "nonzero_control": {"rows": rows, "weights": weights},
        "explicit_regularization": "No explicit penalty in MSELoss; Adam called with lr only",
        "adam_default_weight_decay": torch.optim.Adam(
            control.fm.parameters(), lr=0.01
        ).defaults["weight_decay"],
        "historical_zero_scale_occurrence": "Not established: no historical fitted-weight snapshots; selected logs show no such fit exception.",
    }


def worker(directory):
    from .verify import verify_inputs

    selection = verify_inputs(directory)
    output = directory / "fmqa"
    output.mkdir(exist_ok=False)
    save(output / "environment.json", environment())
    summaries = []
    ledger = []
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="review-fmqa-source-") as temporary:
        for case in selection["fmqa_cases"]:
            qhd, optimizer = load_historical(case, Path(temporary))
            local = directory / "inputs" / case["case"]
            proposals = records((local / "proposals.jsonl").read_bytes())
            events = records((local / case["events_name"]).read_bytes())
            if case["case"] == "rosenbrock":
                events = [e for e in events if e.get("event") == "evaluation"]
            encoding = optimizer.BinaryCoordinates(case["lower"], case["upper"])
            if not (output / "synthetic.json").exists():
                save(output / "synthetic.json", synthetic(qhd))
            for selection_row in case["iterations"]:
                if len(ledger) >= 9 or time.monotonic() - start >= 1200:
                    raise RuntimeError("Diagnostic fit/time cap reached")
                proposal = next(
                    p for p in proposals if p["iteration"] == selection_row["iteration"]
                )
                prefix = events[: proposal["training_points"]]
                points = [tuple(e["point"]) for e in prefix]
                values = [
                    e.get("raw_value")
                    if case["case"] == "rosenbrock"
                    else e["raw_objective"]
                    for e in prefix
                ]
                import numpy as np

                targets = optimizer.training_targets(
                    [float("inf") if v is None else v for v in values]
                )
                if not np.array_equal(targets, np.array(proposal["training_targets"])):
                    raise ValueError(
                        "Recorded targets differ from historical-prefix reconstruction"
                    )
                name = f"{case['case']}_iteration{proposal['iteration']}"
                dest = output / name
                dest.mkdir()
                save(
                    dest / "training_prefix.json",
                    {
                        "kind": "reconstructed diagnostic fit",
                        "points": points,
                        "raw_values": values,
                        "training_targets": proposal["training_targets"],
                        "fm_seed": proposal["fm_seed"],
                        "sa_seed": proposal["sa_seed"],
                        "settings": case["settings"],
                    },
                )
                if encoding.n_bits > 10:
                    save(
                        dest / "result.json",
                        {"status": "not_run", "reason": "more than ten bits"},
                    )
                    continue
                entry = {
                    "case": case["case"],
                    "iteration": proposal["iteration"],
                    "started": True,
                    "completed": False,
                }
                ledger.append(entry)
                save(output / "fit_ledger.json", ledger)
                t = time.monotonic()
                model = qhd.train(
                    [encoding.encode(p) for p in points],
                    targets,
                    seed=proposal["fm_seed"],
                    epochs=case["settings"]["epochs"],
                    learning_rate=case["settings"]["learning_rate"],
                )
                fit_wall = time.monotonic() - t
                entry.update(completed=True, wall_s=fit_wall)
                save(output / "fit_ledger.json", ledger)
                rows, weights = exhaustive(model, encoding, set(points))
                save(
                    dest / "weights.json",
                    {
                        "kind": "reconstructed diagnostic fit; not historical weights",
                        **weights,
                    },
                )
                writecsv(dest / "exhaustive_energy.csv", rows)
                indexed = {r["bits"]: r for r in rows}
                comparisons = []
                for sample in proposal["samples"]:
                    r = indexed[sample["bits"]]
                    if (
                        r["classification"] != sample["classification"]
                        or r["point"] != sample["point"]
                    ):
                        raise ValueError(
                            "Historical domain/seen classification mismatch"
                        )
                    e = r["bqm_scaled_energy_with_offset"]
                    comparisons.append(
                        {
                            **sample,
                            "reconstructed_energy": e,
                            "absolute_difference": abs(e - sample["energy"]),
                            "matches_within_tolerance": check_close(
                                e, sample["energy"], SAMPLE_ATOL, RTOL
                            ),
                        }
                    )
                writecsv(dest / "recorded_sample_comparison.csv", comparisons)
                best = min(r["bqm_scaled_energy_with_offset"] for r in rows)
                ties = [
                    r
                    for r in rows
                    if abs(r["bqm_scaled_energy_with_offset"] - best) <= 1e-10
                ]
                eligible = [r for r in rows if r["eligible"]]
                eligible_best = (
                    min(r["bqm_scaled_energy_with_offset"] for r in eligible)
                    if eligible
                    else None
                )
                selected = indexed[encoding.encode(proposal["selected_point"])]
                if not selected["eligible"]:
                    raise ValueError("Historical proposal is not eligible")
                sampled_eligible = [
                    s for s in comparisons if s["classification"] == "eligible"
                ]
                summary = {
                    "case": case["case"],
                    "iteration": proposal["iteration"],
                    "kind": "reconstructed diagnostic fit",
                    "bits": encoding.n_bits,
                    "binary_strings": len(rows),
                    "training_points": len(prefix),
                    "fit_wall_s": fit_wall,
                    "identity_pass": all(r["identity_pass"] for r in rows),
                    "maximum_identity_absolute_error": max(
                        r["maximum_absolute_identity_error"] for r in rows
                    ),
                    "maximum_identity_relative_error": max(
                        r["maximum_relative_identity_error"] for r in rows
                    ),
                    "absolute_tolerance": ATOL,
                    "relative_tolerance": RTOL,
                    "global_binary_minimum_scaled": best,
                    "minimum_ties_at_1e_10": len(ties),
                    "minimum_out_of_domain": sum(not r["valid_domain"] for r in ties),
                    "minimum_already_evaluated": sum(
                        r["already_evaluated"] for r in ties
                    ),
                    "minimum_eligible": sum(r["eligible"] for r in ties),
                    "eligible_minimum_scaled": eligible_best,
                    "recorded_sample_minimum_scaled": min(
                        s["energy"] for s in comparisons
                    ),
                    "recorded_eligible_sample_minimum_scaled": min(
                        (s["energy"] for s in sampled_eligible), default=None
                    ),
                    "reconstructed_sample_minimum_scaled": min(
                        s["reconstructed_energy"] for s in comparisons
                    ),
                    "reconstructed_eligible_sample_minimum_scaled": min(
                        (s["reconstructed_energy"] for s in sampled_eligible),
                        default=None,
                    ),
                    "selected_point": proposal["selected_point"],
                    "selected_energy_scaled": selected["bqm_scaled_energy_with_offset"],
                    "selected_minus_eligible_minimum": None
                    if eligible_best is None
                    else selected["bqm_scaled_energy_with_offset"] - eligible_best,
                    "proposal_source": proposal["source"],
                    "uniform_fallback": proposal["source"] == "uniform_unseen_fallback",
                    "all_recorded_sample_energies_match": all(
                        s["matches_within_tolerance"] for s in comparisons
                    ),
                    "maximum_recorded_sample_energy_difference": max(
                        s["absolute_difference"] for s in comparisons
                    ),
                    "sample_match_absolute_tolerance": SAMPLE_ATOL,
                    "sample_match_relative_tolerance": RTOL,
                    "historical_SA_optimality_miss": None,
                    "correspondence_limit": "Stored sample energies compared only; no historical weight snapshot or unsampled energy identity established.",
                    "new_sa_calls": 0,
                }
                save(dest / "summary.json", summary)
                summaries.append(summary)
                writecsv(output / "summary.csv", summaries)
                print(
                    "DIAGNOSTIC", name, "identity", summary["identity_pass"], flush=True
                )
    save(
        output / "manifest.json",
        {
            "status": "completed",
            "kind": "reconstructed diagnostic models",
            "selection_sha256": sha(directory / "selection.json"),
            "fits": len(ledger),
            "sa_calls": 0,
            "synthetic_fits": 0,
            "wall_s": time.monotonic() - start,
            "environment": environment(),
            "outputs_sha256": outputs(output),
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    directory = args.directory.resolve()
    if args.worker:
        worker(directory)
    else:
        if (directory / "fmqa_execution.json").exists() or (
            directory / "fmqa"
        ).exists():
            raise FileExistsError(
                "Diagnostic execution already attempted; do not repeat fits"
            )
        save(directory / "fmqa_execution.json", {"status": "started", "limit_s": 1200})
        r = bounded(
            [
                sys.executable,
                "-m",
                "review_diagnostics.fmqa",
                "--directory",
                str(directory),
                "--worker",
            ],
            directory / "fmqa_worker.log",
            1200,
        )
        save(directory / "fmqa_execution.json", r)
        print(r)


if __name__ == "__main__":
    main()
