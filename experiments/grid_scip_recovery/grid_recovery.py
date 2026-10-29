"""Explicit recovery policy for the 46 October 25 Grid errors, not old results."""
from contextlib import contextmanager
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import time

POLICY = "grid-scip-network-and-bohachevsky2-v1"
BACKOFF = (5.0, 15.0)


def network_failure(text):
    if "Curl error: Server returned nothing (no headers, no data)." not in text:
        return None
    for phase in ("start", "close"):
        if f"Error when trying to {phase} network session" in text:
            return phase
    return None


def model_state(model):
    import pyomo.environ as pyo
    # TimedGAMS uses load_solutions=False until the interface returns normally.
    # Refuse transport retries if a failed interface changed the model state.
    return tuple((v.name, v.value, v.lb, v.ub, v.fixed)
                 for v in model.component_data_objects(pyo.Var, descend_into=True))


def emit(path, event):
    from gdp_models.comparison import append_event
    append_event(path, event)


def retry_solve(original, solver, model, kwargs, context, *, sleep=time.sleep):
    """Retry only logged transport errors within the same original deadline."""
    log = context.directory / "run.log"
    events = context.directory / "network_recovery.jsonl"
    initial = model_state(model)
    group = len(context.calls) + 1
    for attempt in range(1, len(BACKOFF) + 2):
        sys.stdout.flush()
        sys.stderr.flush()
        offset = log.stat().st_size if log.exists() else 0
        before = len(context.calls)
        try:
            result = original(solver, model, **kwargs)
        except RuntimeError:
            sys.stdout.flush()
            sys.stderr.flush()
            with log.open("rb") if log.exists() else io.BytesIO() as stream:
                stream.seek(offset)
                delta = stream.read()
            phase = network_failure(delta.decode(errors="replace"))
            if not phase or len(context.calls) != before + 1 or context.calls[-1]["status"] != "error":
                raise
            event = dict(policy=POLICY, group_first_call=group, attempt=attempt,
                         failed_call_index=context.calls[-1]["index"], network_phase=phase,
                         log_start_byte=offset, log_end_byte=offset + len(delta),
                         log_delta_sha256=hashlib.sha256(delta).hexdigest(),
                         original_deadline=context.deadline)
            if model_state(model) != initial:
                emit(events, {**event, "decision": "stop_model_changed"})
                raise
            if attempt > len(BACKOFF):
                emit(events, {**event, "decision": "stop_retry_limit"})
                raise
            delay = BACKOFF[attempt - 1]
            try:
                remaining = context.remaining()
            except Exception:
                emit(events, {**event, "decision": "stop_budget_exhausted"})
                raise
            # Observed network session failures consume about 60 seconds.
            if remaining < delay + 65:
                emit(events, {**event, "decision": "stop_insufficient_budget", "remaining_s": remaining})
                raise
            emit(events, {**event, "decision": "retry_same_interface_call", "backoff_s": delay,
                          "remaining_s": remaining})
            print(f"NETWORK_RECOVERY call={event['failed_call_index']} phase={phase} "
                  f"retry={attempt}/2 delay={delay}s remaining={remaining:.1f}s", flush=True)
            sleep(delay)
        else:
            if attempt > 1:
                emit(events, dict(policy=POLICY, group_first_call=group, attempt=attempt,
                                  decision="interface_returned", returned_call_index=context.calls[-1]["index"],
                                  original_deadline=context.deadline))
            return result


@contextmanager
def bohachevsky2_fbbt(enabled):
    """Keep constant exponent intervals exact without changing model algebra."""
    import pyomo.environ as pyo
    from pyomo.version import version
    from pyomo.core.expr.numeric_expr import PowExpression
    if version != "6.10.0":
        raise ValueError(f"{POLICY} requires Pyomo 6.10.0, observed {version}")
    module = importlib.import_module("pyomo.contrib.fbbt.fbbt")
    dispatch = module._prop_bnds_root_to_leaf_map
    original = dispatch[PowExpression]
    audit = {"bohachevsky2_fixed_exponent_bound_resets": 0}

    def fixed_power(node, bounds, tolerance):
        exponent = node.args[1]
        if pyo.is_fixed(exponent):
            value = pyo.value(exponent)
            if bounds[exponent] != (value, value):
                bounds[exponent] = (value, value)
                audit["bohachevsky2_fixed_exponent_bound_resets"] += 1
        return original(node, bounds, tolerance)

    try:
        if enabled:
            dispatch[PowExpression] = fixed_power
        yield audit
    finally:
        dispatch[PowExpression] = original


def install_worker(experiment):
    """Install only in this package; original model/solver modules stay intact."""
    original_worker = experiment.worker

    def recovery_worker(template, method, directory, config, deadline):
        from gdp_models import comparison as impl
        directory = Path(directory)
        original_solve = impl.TimedGAMS.solve
        policy = dict(policy=POLICY, max_attempts_per_network_call=3, backoff_seconds=BACKOFF,
                      shared_original_deadline=deadline, time_limit=config["time_limit"],
                      selected_from="original status=error only", warmstart=False)
        impl.save_json(directory / "recovery_policy.json", policy)

        def solve(self, model, **kwargs):
            return retry_solve(original_solve, self, model, kwargs, impl.CONTEXT)

        try:
            impl.TimedGAMS.solve = solve
            with bohachevsky2_fbbt(template.metadata.get("grid_name") == "bohachevsky2") as audit:
                original_worker(template, method, directory, config, deadline)
            path = directory / "result.json"
            if path.exists():
                result = json.loads(path.read_text())
                result.update(recovery_policy=POLICY, **audit)
                impl.save_json(path, result)
        finally:
            impl.TimedGAMS.solve = original_solve

    experiment.worker = recovery_worker
