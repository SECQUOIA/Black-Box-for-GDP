"""Load pinned upstream sources without importing their experiment drivers."""

import ast
from functools import lru_cache
import hashlib
import json
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
        # A release companion expands exact gitlink blobs without Git metadata.
        # Never accept an arbitrary unversioned source directory.
        manifest_path = base.parent / "PACKAGE_MANIFEST.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(
                f"Missing source checkout: {root}. Run git submodule update --init."
            )
        manifest = json.loads(manifest_path.read_text())
        prefix = root.relative_to(base.parent).as_posix() + "/"
        if manifest.get("submodules", {}).get(prefix.rstrip("/")) != PINS[name]:
            raise RuntimeError(f"{name}: package does not identify the pinned revision")
        records = [r for r in manifest["files"] if r["path"].startswith(prefix)]
        if not records:
            raise RuntimeError(f"{name}: package source inventory is empty")
        for record in records:
            path = (base.parent / record["path"]).resolve()
            if (not path.is_relative_to(root.resolve()) or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]):
                raise RuntimeError(f"{name}: packaged source hash mismatch: {record['path']}")
        return root
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
