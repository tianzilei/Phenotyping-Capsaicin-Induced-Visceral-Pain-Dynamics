"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from functools import lru_cache
import math
from pathlib import Path
import sys
import numpy as np
from scipy.stats import binom

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]


@lru_cache(maxsize=None)
def enumerated_ranks(n, probability, gamma):
    """Include sentinel ranks; directly enumerate both binomial inequalities."""
    if n < 1 or not 0 < probability < 1 or (not 0 < gamma < 1):
        raise ValueError("Invalid MC rank parameters")
    lower = np.arange(n + 1)
    upper = np.arange(1, n + 2)
    r = int(lower[binom.cdf(lower - 1, n, probability) <= gamma / 2][-1])
    s = int(upper[binom.sf(upper - 1, n, probability) <= gamma / 2][0])
    return (r, s)


def independently_summarize(values, gamma, bounds):
    ordered = np.sort(np.asarray(values, float))
    if not len(ordered) or not np.isfinite(ordered).all():
        raise ValueError("Expected finite successful replicate statistics")
    result = {}
    for label, probability in [("lower", 0.025), ("upper", 0.975)]:
        r, s = enumerated_ranks(len(ordered), probability, gamma)
        estimate = float(ordered[math.ceil(len(ordered) * probability) - 1])
        low = float(ordered[r - 1]) if r else bounds[0]
        high = float(ordered[s - 1]) if s <= len(ordered) else bounds[1]
        half = (
            None
            if low is None or high is None
            else max(estimate - low, high - estimate)
        )
        result[label] = dict(
            estimate=estimate,
            lower_MC=low,
            upper_MC=high,
            lower_rank=r,
            upper_rank=s,
            MC_half_width=half,
        )
    result["empirical_range_width"] = (
        result["upper"]["estimate"] - result["lower"]["estimate"]
    )
    halves = [result[k]["MC_half_width"] for k in ["lower", "upper"]]
    result["MC_max_endpoint_half_width"] = max(halves) if None not in halves else None
    return result


def numeric_equal(actual, expected, label, rtol=1e-12, atol=1e-12):
    if isinstance(expected, dict):
        for key, value in expected.items():
            numeric_equal(actual[key], value, label + "." + key, rtol, atol)
    elif expected is None:
        if actual is not None:
            raise ValueError("Unexpected defined value: " + label)
    elif isinstance(expected, (float, list, np.ndarray)):
        if np.shape(actual) != np.shape(expected) or not np.allclose(
            actual, expected, rtol=rtol, atol=atol
        ):
            raise ValueError("Numerical verification failed: " + label)
    elif actual != expected:
        raise ValueError("Discrete verification failed: " + label)


def verify_reconstruction_numerics(items):
    """Independent NumPy SVD, executed on a remote worker by the caller."""
    import numpy as np

    maxima = dict(
        training_mean=0.0,
        person_constant_rmse=0.0,
        rmse_k0_to_4=0.0,
        paired_loss_difference=0.0,
    )
    for request, saved in items:
        y = np.asarray(request["data"]["y"], float)
        tr, te = (np.asarray(request["train"]), np.asarray(request["test"]))
        if set(tr) & set(te) or sorted(list(tr) + list(te)) != list(range(len(y))):
            raise ValueError("Subject leakage or incomplete fold")
        if saved["train_rows"] != tr.tolist() or saved["test_rows"] != te.tolist():
            raise ValueError("Saved fold differs from frozen fold")
        weights = np.ones(y.shape[1])
        weights[[0, -1]] = 0.5
        mean = y[tr].mean(axis=0)
        _, _, vt = np.linalg.svd((y[tr] - mean) * np.sqrt(weights), full_matrices=False)
        centered = (y[te] - mean) * np.sqrt(weights)
        constant = y[te] @ weights / weights.sum()
        baseline = np.sqrt((y[te] - constant[:, None]) ** 2 @ weights / weights.sum())
        errors = []
        for k in range(5):
            residual = centered if k == 0 else centered - centered @ vt[:k].T @ vt[:k]
            errors.append(np.sqrt((residual**2).sum(axis=1) / weights.sum()))
        errors = np.array(errors).T
        values = dict(
            training_mean=mean,
            person_constant_rmse=baseline,
            rmse_k0_to_4=errors,
            paired_loss_difference=errors - baseline[:, None],
        )
        for key, expected in values.items():
            actual = np.asarray(saved[key], float)
            if actual.shape != expected.shape or not np.allclose(
                actual, expected, rtol=1e-08, atol=1e-09
            ):
                raise ValueError("Independent heldout reconstruction mismatch: " + key)
            maxima[key] = max(maxima[key], float(np.max(np.abs(actual - expected))))
    return dict(status="PASS", folds=len(items), max_absolute_difference=maxima)


def portable_reconstruction_checker():
    from types import FunctionType

    return FunctionType(
        verify_reconstruction_numerics.__code__,
        {"__builtins__": __builtins__, "__name__": "__main__"},
        "independent_reconstruction_checker",
    )
