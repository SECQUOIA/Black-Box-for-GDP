"""External-integer domains of the pinned GDP formulations (no objective data)."""

from itertools import product


def enumeration_plan(case, *, cstr_size=5, domain="logical"):
    """Lexicographic candidates; logical validity does not imply NLP feasibility.

    ``box`` includes every external-integer tuple within the original bounds.
    ``logical`` removes only tuples ruled out by the original GDP logic.
    Column's minimum-tray algebraic constraint is left to preprocessing.
    """
    if domain not in {"logical", "box"}:
        raise ValueError("domain must be logical or box")
    if case == "cstr":
        if isinstance(cstr_size, bool) or int(cstr_size) != cstr_size or cstr_size < 1:
            raise ValueError("cstr_size must be a positive integer")
        bounds = [(1, int(cstr_size))] * 2
        def valid(x):
            return x[1] <= x[0]
        rule = "recycle_position <= feed_position"
    elif case == "column":
        bounds = [(1, 15)] * 2
        # The pinned 17-tray model has feed tray 9. External position 8
        # denotes that physical tray: reflux >= feed, boilup <= feed.
        def valid(x):
            return x[0] >= 8 and x[1] <= 8
        rule = "reflux_position >= 8 and boilup_position <= 8"
    elif case == "small_batch":
        bounds = [(1, 3)] * 3
        def valid(x):
            return True
        rule = "all three unit counts in 1..3"
    elif case == "dynamic":
        bounds = [(1, 9), (2, 9)]
        def valid(x):
            return x[0] < x[1] or x == (9, 9)
        rule = "last_mode1_stage < last_mode2_stage, or (9,9)"
    else:
        raise ValueError(f"Unknown case: {case}")
    box = product(*(range(lo, hi + 1) for lo, hi in bounds))
    points = [list(p) for p in box if domain == "box" or valid(p)]
    raw_count = 1
    for lo, hi in bounds:
        raw_count *= hi - lo + 1
    return {
        "case": case, "cstr_size": int(cstr_size) if case == "cstr" else None,
        "domain": domain, "bounds": [list(b) for b in bounds],
        "logical_rule": rule, "box_count": raw_count,
        "candidate_count": len(points), "excluded_by_logic": raw_count - len(points),
        "points": points,
    }
