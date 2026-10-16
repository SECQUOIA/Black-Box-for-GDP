"""Unmodified QHD_Data PyTorch FMBQM, with deterministic CPU seeding."""

import ast
from functools import lru_cache
import importlib.util
import json
import math
from pathlib import Path
import sys

from .protocol import sha

VENDOR = Path(__file__).with_name("vendor") / "qhd"
COMMIT = "eb3a20d4b5a3773d17ff31d72a35d51f58e84e56"


def verify_sources():
    provenance = json.loads((VENDOR / "provenance.json").read_text())
    if provenance["commit"] != COMMIT or provenance["branch"] != "QHD_Data":
        raise ValueError("Unexpected PyTorch source revision")
    for name, digest in provenance["files_sha256"].items():
        if sha(VENDOR / name) != digest:
            raise ValueError(f"QHD_Data source changed: {name}")
    return provenance


@lru_cache(maxsize=1)
def upstream():
    import numpy as np
    verify_sources()
    name = "_benchmark_qhd_fmqa"
    path = VENDOR / "fmqa/fmqa/__init__.py"
    spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=[str(path.parent)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    path = VENDOR / "bbo_via_fmqa/ml_surrogate.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "train_surrogate_model"]
    if len(tree.body) != 1:
        raise ValueError("Missing original QHD_Data training entry point")
    scope = {"np": np, "FMBQM": module.FMBQM}
    exec(compile(tree, str(path), "exec"), scope)
    return module, scope["train_surrogate_model"]


def cpu_settings():
    import torch
    torch.set_num_threads(1)
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    torch.set_default_dtype(torch.float32)
    torch.set_default_device("cpu")
    torch.use_deterministic_algorithms(True)
    return {"device": "cpu", "dtype": "float32", "threads": torch.get_num_threads(),
            "interop_threads": torch.get_num_interop_threads(),
            "deterministic_algorithms": torch.are_deterministic_algorithms_enabled()}


def train(bits, targets, *, seed, epochs, learning_rate, stop_check=lambda: None):
    import numpy as np
    import torch
    cpu_settings()
    if (not bits or not bits[0] or any(len(b) != len(bits[0]) or set(b) - {"0", "1"} for b in bits)
            or len(targets) != len(bits) or not np.isfinite(targets).all()
            or epochs < 1 or not math.isfinite(learning_rate) or learning_rate <= 0):
        raise ValueError("Invalid FM training observations or settings")
    stop_check()
    _, original_train = upstream()
    # Preserve the upstream float32 model, zero bias, initialization order,
    # MSELoss, Adam update and coefficient scaling without porting them again.
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        model = original_train(bits, targets, num_epoch=epochs, learning_rate=learning_rate)
    stop_check()
    if (any(p.device.type != "cpu" or p.dtype != torch.float32 for p in model.fm.parameters())
            or not all(math.isfinite(v) for v in (*model.linear.values(), *model.quadratic.values(), model.offset))):
        raise ValueError("PyTorch FMBQM has invalid coefficients, dtype or device")
    return model
