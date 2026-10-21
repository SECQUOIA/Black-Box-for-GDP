"""Optional prerequisites for solver-free GDP diagnostic tests."""

from pathlib import Path

import pytest


@pytest.fixture
def pyomo_env():
    return pytest.importorskip("pyomo.environ")


@pytest.fixture
def cstr_diagnostic_sources(pyomo_env):
    pytest.importorskip("sympy")
    pytest.importorskip("networkx")
    source = Path(__file__).resolve().parents[1] / "external/dsda-gdp"
    if not (source / ".git").exists() or not (source / "gdp/cstr/gdp_reactor.py").is_file():
        pytest.skip("Initialize external/dsda-gdp to run CSTR diagnostic tests")
    return pyomo_env
