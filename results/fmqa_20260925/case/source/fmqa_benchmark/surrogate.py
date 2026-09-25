"""CPU NumPy port of TsudaLab FMBQM; original SECQUOIA training entry point.

The rank-8 FM, normal(0, .01) initialization, Adam and coefficient normalization
follow the pinned MXNet implementation. Floating point and random streams differ;
this is explicitly a port, not a bit-for-bit reproduction of MXNet trajectories.
See vendor/tsudalab/LICENSE and docs/fmqa_benchmark.md.
"""

import ast
from functools import lru_cache
import json
from pathlib import Path
from types import SimpleNamespace

import dimod
import numpy as np

from .protocol import sha


def prediction_and_gradients(x, y, bias, linear, factors):
    projected = x @ factors.T
    prediction = bias[0] + x @ linear + 0.5 * np.sum(
        projected**2 - x**2 @ (factors**2).T, axis=1)
    residual = prediction - y
    scale = 2.0 / len(x)
    gradients = (
        np.array([scale * residual.sum()]),
        scale * (x.T @ residual),
        scale * ((residual[:, None] * projected).T @ x
                 - factors * (residual @ x**2)[None, :]),
    )
    return prediction, gradients


def fit_bqm(x, y, *, seed, num_epoch=1000, learning_rate=1e-2, stop_check=lambda: None):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if (x.ndim != 2 or y.shape != (len(x),) or not len(x)
            or not x.shape[1] or not np.isin(x, (0, 1)).all() or not np.isfinite(y).all()):
        raise ValueError("FM training requires finite targets and a binary feature matrix")
    if num_epoch < 1 or not np.isfinite(learning_rate) or learning_rate <= 0:
        raise ValueError("FM epochs and learning rate must be positive and finite")
    rng = np.random.default_rng(seed)
    parameters = [rng.normal(0, .01, 1), rng.normal(0, .01, x.shape[1]),
                  rng.normal(0, .01, (8, x.shape[1]))]
    moments = [np.zeros_like(p) for p in parameters]
    variances = [np.zeros_like(p) for p in parameters]
    for epoch in range(1, num_epoch + 1):
        if epoch % 50 == 1:
            stop_check()
        _, gradients = prediction_and_gradients(x, y, *parameters)
        for p, m, v, g in zip(parameters, moments, variances, gradients):
            # The upstream code uses mean-square loss then Trainer.step(batchsize).
            g = g / len(x)
            m *= .9
            m += .1 * g
            v *= .999
            v += .001 * g**2
            # MXNet 1.8 applies bias correction to lr, with epsilon outside
            # the uncorrected second-moment square root (optimizer.Adam.update).
            rate = learning_rate * np.sqrt(1 - .999**epoch) / (1 - .9**epoch)
            p -= rate * m / (np.sqrt(v) + 1e-8)
    bias, linear, factors = parameters
    q = np.triu(factors.T @ factors, k=1)
    np.fill_diagonal(q, linear)
    coefficient_scale = float(np.max(np.abs(q)))
    if coefficient_scale == 0:
        coefficient_scale = 1.0
    q /= coefficient_scale
    if not np.isfinite(q).all() or not np.isfinite(bias).all():
        raise FloatingPointError("FM coefficients became nonfinite")
    bqm = dimod.BinaryQuadraticModel(
        {i: q[i, i] for i in range(x.shape[1])},
        {(i, j): q[i, j] for i in range(x.shape[1]) for j in range(i + 1, x.shape[1])},
        float(bias[0] / coefficient_scale), dimod.BINARY)
    return bqm


@lru_cache(maxsize=1)
def upstream_code():
    vendor = Path(__file__).with_name("vendor")
    meta = json.loads((vendor / "provenance.json").read_text())
    relative = "bbo_via_fmqa/ml_surrogate.py"
    path = vendor / "bbo_via_fmqa" / relative
    if sha(path) != meta["bbo_via_fmqa"]["files_sha256"][relative]:
        raise ValueError("Pinned SECQUOIA training function checksum mismatch")
    tree = ast.parse(path.read_text(), filename=str(path))
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "train_surrogate_model"]
    if len(tree.body) != 1:
        raise ValueError("Missing upstream training function")
    return compile(tree, str(path), "exec")


def train(bits, targets, *, seed, epochs, learning_rate, stop_check=lambda: None):
    def from_data(x, y, num_epoch, learning_rate):
        return fit_bqm(x, y, seed=seed, num_epoch=num_epoch,
                       learning_rate=learning_rate, stop_check=stop_check)

    scope = {"np": np, "FMBQM": SimpleNamespace(from_data=from_data)}
    exec(upstream_code(), scope)
    return scope["train_surrogate_model"](
        bits, targets, num_epoch=epochs, learning_rate=learning_rate)
