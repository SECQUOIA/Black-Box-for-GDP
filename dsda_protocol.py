"""Maintained D-SDA movement and observed-target protocol.

Movement, numerical ties, target proximity, and response acceptance are distinct.
Target proximity is a reference comparison, not a proof of global optimality.
"""

import math

from instrumentation import TrackedObjective

IMPROVEMENT_ABS_TOL = 1e-5
TARGET_TOL = 1e-5


def validate_tolerances(tol, improvement_abs_tol):
    for name, value in (("tol", tol), ("improvement_abs_tol", improvement_abs_tol)):
        if name == "improvement_abs_tol" and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be finite and nonnegative")
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and nonnegative")


def improves(new_value, old_value, maximize=False, tol=1e-12,
             improvement_abs_tol=IMPROVEMENT_ABS_TOL):
    """Strict absolute movement; None explicitly requests legacy arithmetic."""
    validate_tolerances(tol, improvement_abs_tol)
    if improvement_abs_tol is None:
        return new_value > old_value + tol if maximize else new_value < old_value - tol
    # Invalid responses never become moves; a finite observation can recover an
    # invalid start without converting a failed response into an incumbent.
    if not math.isfinite(new_value):
        return False
    if not math.isfinite(old_value):
        return True
    difference = new_value - old_value if maximize else old_value - new_value
    return difference > improvement_abs_tol


def common_target_reached(observed_best, target):
    """The adopted analysis predicate, applied to unrounded finite values."""
    if observed_best is None or target is None:
        return False
    return (math.isfinite(observed_best) and math.isfinite(target)
            and abs(observed_best - target) <= TARGET_TOL * max(1.0, abs(target)))


class ObservedObjective(TrackedObjective):
    """Count all callbacks, but track only finite accepted response values.

The objective still returns its original penalty or invalid response to search.
This tracker does not filter neighbors, rank starts, or accept moves.
"""

    def __init__(self, objective, maximize=False, penalty=None, legacy=False):
        super().__init__(objective, maximize=maximize)
        self.penalty = penalty
        self.legacy = legacy
        self.observed_incumbent = None

    def _update_incumbent(self, value):
        accepted = math.isfinite(value) and value != self.penalty
        if accepted and (self.observed_incumbent is None or (
            value > self.observed_incumbent if self._maximize
            else value < self.observed_incumbent
        )):
            self.observed_incumbent = value
        if accepted or self.legacy:
            super()._update_incumbent(value)


def add_target_report(result, observed_best, target):
    """Add common reporting without changing path-selected best/legacy flags."""
    report = {
        "observed_best_value": observed_best,
        "target_reached": common_target_reached(observed_best, target),
    }
    result.update(report)
    result["result_record"].update(report)
