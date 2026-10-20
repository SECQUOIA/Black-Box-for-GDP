"""Independent checks for the retained-return verifier; no optimization calls."""

import copy
import zipfile

import pytest

from review_comparison.audit import audit_events, verified_return
from review_comparison.common import sha


@pytest.fixture
def recorded():
    job = {"scope": "process", "case": "column", "budget": 3,
           "lower": [1, 1], "upper": [2, 2], "starts": [[1, 1], [1, 2], [1, 1]]}
    costs = {(1, 1): (1.0, {"accepted": "True", "objective": "3"}),
             (1, 2): (0.5, {"accepted": "False", "objective": ""})}
    events = [{"index": i, "point": p, "accepted": i != 2,
               "raw_objective": 3.0 if i != 2 else None,
               "method_value": 3.0 if i != 2 else 1e6, "method_value_kind": "finite",
               "failure_reason": None if i != 2 else "solver failure; no feasible result",
               "historical_point_cost_s": 1.0 if i != 2 else 0.5,
               "lookup_wall_s": 0.01, "value_returned_to_optimizer": i != 3}
              for i, p in enumerate(job["starts"], 1)]
    result = {"status": "budget_completed", "evaluations": 3, "target": 3.0,
              "best_objective": 3.0, "best_point": [1, 1], "target_observed": True,
              "category": "target_reached", "missing_cost_callbacks": 0,
              "one_time_preparation_s": 0.0, "sum_point_cost_s": 2.5,
              "lookup_wall_s": 0.03, "recorded_search_wall_s": 0.3,
              "retained_search_wall_s": 0.27, "reconstructed_total_s": 2.77}
    return job, events, result, costs, 0.0


def test_repeated_failed_and_terminal_callbacks_are_all_charged(recorded):
    counts = audit_events(*recorded)
    assert counts == {"callbacks": 3, "accepted_callbacks": 2, "unaccepted_callbacks": 1,
                      "repeat_callbacks": 1, "initial_accepted": 2, "last_callback_delivered": False}


@pytest.mark.parametrize("change", ["objective", "acceptance", "missing_cost", "zero_time", "penalty", "reason", "budget", "category"])
def test_inconsistent_results_rejected(recorded, change):
    job, events, result, costs, prep = copy.deepcopy(recorded)
    if change == "objective":
        events[0]["raw_objective"] = 2
    elif change == "acceptance":
        events[1]["accepted"] = True
    elif change == "missing_cost":
        del costs[1, 2]
    elif change == "zero_time":
        costs[1, 2] = (0.0, costs[1, 2][1])
    elif change == "penalty":
        events[1]["method_value"] = 0
    elif change == "reason":
        events[1]["failure_reason"] = None
    elif change == "budget":
        job["budget"] = 2
    else:
        result["category"] = "target_not_reached"
    with pytest.raises(ValueError):
        audit_events(job, events, result, costs, prep)


def test_archive_requires_exact_digest_and_safe_members(tmp_path):
    archive = tmp_path / "return.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("run/value.txt", "original")
    digest = sha(archive)
    with verified_return(archive, digest) as (root, count):
        assert count == 1 and (root / "value.txt").read_text() == "original"
    with pytest.raises(ValueError, match="SHA256"):
        with verified_return(archive, "wrong"):
            pass
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("run/../escape.txt", "unsafe")
    with pytest.raises(ValueError, match="Unsafe"):
        with verified_return(archive, sha(archive)):
            pass
