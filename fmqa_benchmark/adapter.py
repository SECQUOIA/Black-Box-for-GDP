"""Public benchmark adapter around the pinned upstream FM core."""

from .optimizer import optimize
from .qhd_surrogate import COMMIT, verify_sources

DEFAULT_CONFIG = {
    "epochs": 1000,
    "learning_rate": 0.01,
    "num_reads": 100,
    "num_sweeps": 1000,
    "time_limit": 1800,
}


def run_fmqa_sa(objective, lower, upper, starts, budget, seed, *, config=None,
                on_evaluation=lambda event, state: None,
                on_proposal=lambda event: None):
    """Run the benchmark procedure with an opaque objective callback.

    The caller supplies the ordered common initial design. Only evaluated
    responses reach surrogate training; no table or reference target is used.
    Hooks expose completed evaluations and candidate proposals. Objective
    exceptions propagate; callers needing attempted-call logs should wrap the
    objective (as the IPOPT CSV runners do).
    """
    config = {} if config is None else dict(config)
    unknown = set(config) - set(DEFAULT_CONFIG)
    if unknown:
        raise ValueError(f"Unknown FMQA adapter settings: {sorted(unknown)}")
    settings = {**DEFAULT_CONFIG, **config}
    provenance = verify_sources()
    result = optimize(objective, lower, upper, starts, budget, seed, settings,
                      on_evaluation=on_evaluation, on_proposal=on_proposal)
    result["adapter"] = {
        "protocol": "rbfopt_test_qhd_fmqa_sa_v1",
        "upstream_repository": provenance["repository"],
        "upstream_commit": COMMIT,
        "seed": seed,
        "settings": settings,
        "training_response": "observed finite min-max -> [0,1]; unsuccessful -> 2",
        "sampler": "dwave.samplers.SimulatedAnnealingSampler",
        "fallback": "uniform unseen point from the declared integer box",
    }
    return result
