"""Summaries for E minus N/C/P resting-reference candidate deviations."""

from __future__ import annotations
import numpy as np


def paired_delta(rows, feature):
    values = []
    for row in rows:
        a = row.get("rest_" + feature)
        b = row.get("stimulus_" + feature)
        if a is None or b is None:
            continue
        try:
            a = float(a)
            b = float(b)
        except (TypeError, ValueError):
            continue
        if np.isfinite(a) and np.isfinite(b):
            values.append(b - a)
    return np.asarray(values, dtype=float)


def bootstrap_delta_summary(values, seed=20260929, replicates=5000, alpha=0.05):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return {"n": 0, "median": None, "low": None, "high": None}
    rng = np.random.default_rng(seed)
    draw = np.median(
        values[rng.integers(0, len(values), size=(replicates, len(values)))], axis=1
    )
    return {
        "n": int(len(values)),
        "median": float(np.median(values)),
        "low": float(np.quantile(draw, alpha / 2)),
        "high": float(np.quantile(draw, 1 - alpha / 2)),
    }
