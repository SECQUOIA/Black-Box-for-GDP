"""Missing optional Pyomo dependencies must never become failed NLP results."""

import subprocess
import sys

import pytest

pytest.importorskip("pyomo.environ")


@pytest.mark.parametrize("mode", ["check", "run"])
def test_missing_sympy_aborts_before_enumeration(tmp_path, mode):
    # A fresh interpreter mimics the standalone server environment. Blocking
    # imports also exercises Pyomo's deferred optional-dependency mechanism.
    code = """
import importlib.abc
import sys
class MissingSympy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'sympy' or fullname.startswith('sympy.'):
            raise ModuleNotFoundError("No module named 'sympy'")
sys.meta_path.insert(0, MissingSympy())
from gdp_models.dantzig import main
sys.argv = ['dantzig', sys.argv[1], '--output-root', sys.argv[2]]
raise SystemExit(main())
"""
    directory = tmp_path / "results"
    result = subprocess.run([sys.executable, "-c", code, mode, str(directory)],
                            capture_output=True, text=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Required GDP dependency 'sympy'" in result.stderr
    assert "pip install -r requirements-gdp.txt" in result.stderr
    assert not directory.exists()
