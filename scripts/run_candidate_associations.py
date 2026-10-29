"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def prepare(d, standardize=False):
    d = d.copy()
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    d["vas_mean"] = pd.to_numeric(d["vas_mean"], errors="coerce")
    d = d[np.isfinite(d.value) & np.isfinite(d.vas_mean)]
    if d.duplicated(["person_id", "block"]).any():
        raise ValueError("duplicate person block")
    counts = d.groupby("person_id").block.nunique()
    d = d[d.person_id.isin(counts[counts >= 2].index)]
    if standardize:
        sd = d.groupby("person_id").value.transform("std")
        mean = d.groupby("person_id").value.transform("mean")
        d["value"] = (d.value - mean) / sd
        d = d[np.isfinite(d.value)]
    if len(d) < 5:
        return (None, d)
    people = sorted(d.person_id.unique())
    g = pd.Categorical(d.person_id, categories=people).codes
    x = d.vas_mean.to_numpy(float)
    y = d.value.to_numpy(float)
    z = pd.get_dummies(d.block.astype(int), drop_first=True).to_numpy(float)
    design = np.column_stack([x, y, z])
    design -= pd.DataFrame(design).groupby(g).transform("mean").to_numpy()
    return ((design, g, len(people)), d)


def coefficient(prepared, counts=None):
    if prepared is None:
        return None
    a, g, n = prepared
    w = np.ones(len(a)) if counts is None else counts[g]
    x = a[:, 0]
    y = a[:, 1]
    z = a[:, 2:]
    if w.sum() < 5:
        return None
    if z.shape[1]:
        gram = z.T @ (w[:, None] * z)
        if np.linalg.matrix_rank(gram) < z.shape[1]:
            return None
        x = x - z @ np.linalg.solve(gram, z.T @ (w * x))
        y = y - z @ np.linalg.solve(gram, z.T @ (w * y))
    denominator = np.sum(w * x * x)
    if denominator < 1e-10:
        return None
    return float(np.sum(w * x * y) / denominator)
