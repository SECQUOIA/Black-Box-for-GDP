"""Check the minimal runtime and real GDP-to-NLP transformations before a batch."""

import importlib
import json
from pathlib import Path
import tempfile


class SetupError(RuntimeError):
    """An environment/configuration failure, not an optimization outcome."""


def dependency_versions():
    versions = {}
    for name in ("pyomo", "sympy", "numpy", "networkx", "matplotlib"):
        try:
            module = importlib.import_module(name)
        except ImportError as error:
            raise SetupError(
                f"Required GDP dependency {name!r} cannot be imported: {error}. "
                "Run python -m pip install -r requirements-gdp.txt with the updated runner."
            ) from error
        versions[name] = module.__version__
    return versions


def model_check(case, cstr_size=5, initialization="auto"):
    """Exercise original logic, DAE conversion, presolve and the NLP writer.

    These are preparation checks, not convergence/optimality certificates.
    Every timed evaluation uses an independent model; Dynamic clones the
    discretized template created here instead of repeating DAE conversion.
    """
    from .models import prepare_nlp

    point = {"column": (13, 4), "small_batch": (2, 2, 1),
             "dynamic": (1, 4), "cstr": (min(3, cstr_size), 1)}[case]
    try:
        prepared = prepare_nlp(case, point, cstr_size=cstr_size, initialization=initialization)
        with tempfile.TemporaryDirectory(prefix="gdp-preflight-") as directory:
            prepared.model.write(str(Path(directory) / "model.nl"), format="nl")
    except Exception as error:
        raise SetupError(
            f"GDP preparation check failed for {case} (CSTR size={cstr_size}), "
            f"point={point}: {type(error).__name__}: {error}"
        ) from error
    return {"point": list(point), "status": "nl_written", "solver_called": False}


def main():
    # Runs in CI with ONLY requirements-gdp.txt, without a native solver.
    versions = dependency_versions()
    checks = {case: model_check(case) for case in ("column", "small_batch", "dynamic")}
    checks.update({f"cstr_{size}": model_check("cstr", size)
                   for size in (30,)})
    print(json.dumps({"dependencies": versions, "model_checks": checks}, indent=2))


if __name__ == "__main__":
    main()
