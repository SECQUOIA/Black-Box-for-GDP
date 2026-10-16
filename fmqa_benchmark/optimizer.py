"""Budgeted FMQA-SA loop using only evaluated objective values."""

from dataclasses import dataclass
import itertools
import math
from time import perf_counter

import numpy as np

from .qhd_surrogate import train


PENALTY = 1e6


@dataclass
class BinaryCoordinates:
    lower: list
    upper: list

    def __post_init__(self):
        if len(self.lower) != len(self.upper) or not self.lower:
            raise ValueError("Coordinate bounds must have equal nonzero dimension")
        if any(lo < 0 or hi < lo for lo, hi in zip(self.lower, self.upper)):
            raise ValueError("Binary coordinates require 0 <= lower <= upper")
        self.widths = [max(1, int(hi).bit_length()) for hi in self.upper]

    @property
    def n_bits(self):
        return sum(self.widths)

    def encode(self, point):
        if not self.valid(point):
            raise ValueError(f"Point outside integer bounds: {point}")
        return "".join(format(int(v), f"0{n}b") for v, n in zip(point, self.widths))

    def decode(self, bits):
        if len(bits) != self.n_bits or any(v not in "01" for v in bits):
            raise ValueError("Invalid binary sample")
        point, offset = [], 0
        for width in self.widths:
            point.append(int(bits[offset:offset + width], 2))
            offset += width
        return tuple(point)

    def valid(self, point):
        return len(point) == len(self.lower) and all(
            int(v) == v and lo <= v <= hi for v, lo, hi in zip(point, self.lower, self.upper))

    def lattice(self):
        return list(itertools.product(*(range(lo, hi + 1) for lo, hi in zip(self.lower, self.upper))))


def training_targets(raw_values):
    """Observed feasible values -> [0,1], observed infeasible values -> 2."""
    values = np.asarray(raw_values, dtype=float)
    finite = np.isfinite(values)
    targets = np.full(len(values), 2.0)
    if finite.any():
        low, high = float(values[finite].min()), float(values[finite].max())
        targets[finite] = (values[finite] - low) / (high - low) if high > low else 0.0
    return targets


class BudgetExpired(RuntimeError):
    pass


def optimize(objective, lower, upper, starts, budget, seed, config, *,
             on_evaluation=lambda event, state: None, on_proposal=lambda event: None,
             trainer=train, sampler=None):
    if sampler is None:
        from dwave.samplers import SimulatedAnnealingSampler
        sampler = SimulatedAnnealingSampler()
    encoding = BinaryCoordinates(lower, upper)
    starts = [tuple(p) for p in starts]
    if budget < len(starts) or len(set(starts)) != len(starts) or any(not encoding.valid(p) for p in starts):
        raise ValueError("Invalid initial design or evaluation budget")
    lattice = encoding.lattice()
    if budget > len(lattice):
        raise ValueError("Budget exceeds the number of distinct integer points")
    streams = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(3)]
    model_rng, anneal_rng, fallback_rng = streams
    started = perf_counter()
    deadline = started + config["time_limit"]
    points, values, history = [], [], []
    best, best_point = PENALTY, None
    train_time, sa_time, objective_time, fallbacks = 0.0, 0.0, 0.0, 0

    def check_time():
        if perf_counter() >= deadline:
            raise BudgetExpired("FMQA run time limit reached")

    def snapshot(status):
        return {"status": status, "best_value": best, "best_point": list(best_point) if best_point else [],
                "has_feasible_solution": any(math.isfinite(v) for v in values),
                "total_evals": len(points), "initial_evals": min(len(points), len(starts)),
                "adaptive_evals": max(0, len(points) - len(starts)), "unique_evals": len(set(points)),
                "incumbent_trajectory": list(history), "wall_time_s": perf_counter() - started,
                "training_wall_s": train_time, "annealing_wall_s": sa_time,
                "objective_wall_s": objective_time, "fallback_count": fallbacks,
                "bit_widths": encoding.widths}

    def evaluate(point, phase, source):
        nonlocal best, best_point, objective_time
        check_time()
        t = perf_counter()
        raw = float(objective(point))
        elapsed = perf_counter() - t
        objective_time += elapsed
        if math.isfinite(raw) and raw >= PENALTY:
            raise ValueError("Feasible objective exceeds the declared report penalty")
        value = raw if math.isfinite(raw) else PENALTY
        points.append(tuple(point))
        values.append(raw)
        if best_point is None or value < best:
            best, best_point = value, tuple(point)
        history.append(best)
        on_evaluation({"event": "evaluation", "evaluation_index": len(points),
                       "phase": phase, "point": list(point), "value": value,
                       "raw_value": raw if math.isfinite(raw) else None,
                       "lookup_feasible": math.isfinite(raw), "incumbent": best,
                       "objective_wall_s": elapsed, "completed_elapsed_s": perf_counter() - started,
                       "source": source}, snapshot("running"))

    try:
        for point in starts:
            evaluate(point, "initial", "original_frozen_design")
        while len(points) < budget:
            check_time()
            fm_seed = int(model_rng.integers(0, 2**31 - 1))
            sa_seed = int(anneal_rng.integers(1, 2**31 - 1))
            targets = training_targets(values)
            t = perf_counter()
            model = trainer([encoding.encode(p) for p in points], targets,
                            seed=fm_seed, epochs=config["epochs"], learning_rate=config["learning_rate"],
                            stop_check=check_time)
            train_time += perf_counter() - t
            check_time()
            t = perf_counter()
            samples = sampler.sample(model, num_reads=config["num_reads"], num_sweeps=config["num_sweeps"],
                                     seed=sa_seed, beta_schedule_type="geometric",
                                     interrupt_function=lambda: perf_counter() >= deadline)
            sa_time += perf_counter() - t
            check_time()
            chosen, candidates = None, []
            seen = set(points)
            for sample, energy, count in samples.aggregate().data(["sample", "energy", "num_occurrences"]):
                bits = "".join(str(int(sample[i])) for i in range(encoding.n_bits))
                point = encoding.decode(bits)
                reason = "out_of_bounds" if not encoding.valid(point) else "already_evaluated" if point in seen else "eligible"
                candidates.append({"bits": bits, "point": list(point), "energy": float(energy),
                                   "occurrences": int(count), "classification": reason})
                if chosen is None and reason == "eligible":
                    chosen = point
            source = "simulated_annealing"
            if chosen is None:
                remaining = [p for p in lattice if p not in seen]
                chosen = remaining[int(fallback_rng.integers(len(remaining)))]
                source = "uniform_unseen_fallback"
                fallbacks += 1
            on_proposal({"event": "proposal", "iteration": len(points) - len(starts) + 1,
                         "training_points": len(points), "fm_seed": fm_seed, "sa_seed": sa_seed,
                         "training_targets": targets.tolist(), "selected_point": list(chosen),
                         "source": source, "samples": candidates})
            evaluate(chosen, "adaptive", source)
        return snapshot("completed")
    except BudgetExpired:
        return snapshot("time_limit")
