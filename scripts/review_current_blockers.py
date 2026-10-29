"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def direct_fit(frame):
    """Independent OLS with explicit person and block dummy columns."""
    people = pd.get_dummies(frame.person_id, dtype=float).to_numpy()
    blocks = pd.get_dummies(
        frame.block.astype(int), drop_first=True, dtype=float
    ).to_numpy()
    design = np.column_stack([frame.vas_mean.to_numpy(float), people, blocks])
    if np.linalg.matrix_rank(design) != design.shape[1]:
        raise ValueError("Explicit model rank deficient")
    return float(np.linalg.lstsq(design, frame.value.to_numpy(float), rcond=None)[0][0])
