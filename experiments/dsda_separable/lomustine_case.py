"""Lomustine case with the separable D-SDA neighborhood, for the neighborhood comparison.

Plugs into experiments/catalytic_distillation_live/run.py through LIVE_DFO_CASE, like
experiments/lomustine_simulation/case.py, whose data, option orders (LOMUSTINE_ORDER),
starts, and budgets it reuses unchanged.  Only the D-SDA neighborhood differs: one external
variable changed by +-1 in place of the unit L-infinity neighborhood.  case.py stays
untouched, so the archived Lomustine campaigns still match its hash.
"""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "lomustine_simulation/case.py"
_spec = importlib.util.spec_from_file_location("lomustine_case", _PATH)
_case = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_case)
globals().update({name: value for name, value in vars(_case).items() if not name.startswith("__")})

SETTINGS = {"dsda": {"diagonal": False}}
OPTIONS = {**_case.OPTIONS, "dsda_neighborhood": "separable"}
LOMUSTINE_CASE_SHA256 = _case.sha256(_PATH)
