"""Load pinned upstream sources without importing their experiment drivers."""

import ast
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import subprocess

import pyomo.environ as pyo


PINS = {
    "dsda-gdp": "3e469dbeea8931670b8cd6752014ab7a767d3af5",
    "ld-sda-dynamic": "482e14ebf9caabbd35d959986942cb028778a1d7",
}


@lru_cache(maxsize=None)
def source_root(name):
    base = Path(os.environ.get(
        "RBFOPT_GDP_SOURCES", Path(__file__).resolve().parents[1] / "external"
    ))
    root = base / name
    if not (root / ".git").exists():
        raise FileNotFoundError(
            f"Missing source checkout: {root}. Run git submodule update --init."
        )
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != PINS[name]:
        raise RuntimeError(f"{name}: expected commit {PINS[name]}, found {revision}")
    return root


@lru_cache(maxsize=None)
def load_source(name, relative, functions=()):
    """Compile original definitions; bypass only obsolete, unrelated imports.

    Column imports the removed MasterProblemResult but never uses it. The
    DSDA driver imports other removed APIs, so only its requested helper
    definitions (with unchanged bodies) are compiled.
    """
    path = source_root(name) / relative
    tree = ast.parse(path.read_text(), filename=str(path))
    if functions:
        tree.body = [node for node in tree.body
                     if isinstance(node, ast.FunctionDef) and node.name in functions]
        if {node.name for node in tree.body} != set(functions):
            raise RuntimeError(f"Required upstream functions missing in {path}")
    elif relative == "gdp/column/gdp_column.py":
        tree.body = [node for node in tree.body if not (
            isinstance(node, ast.ImportFrom)
            and node.module == "pyomo.contrib.gdpopt.data_class"
        )]
    scope = {"__file__": str(path), "__name__": "_rbfopt_original_gdp",
             "pe": pyo, "pyo": pyo}
    exec(compile(tree, str(path), "exec"), scope)
    return scope


def provenance(name, files):
    root = source_root(name)
    return {
        "repository": f"https://github.com/SECQUOIA/{'LD-SDA-Dynamic' if name == 'ld-sda-dynamic' else name}",
        "commit": PINS[name],
        # Hash the actual loaded files as well as recording the checkout commit.
        "files_sha256": {f: hashlib.sha256((root / f).read_bytes()).hexdigest()
                         for f in files},
    }
