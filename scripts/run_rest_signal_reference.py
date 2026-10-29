"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]


def quantiles(values):
    x = np.asarray([v for v in values if v is not None and np.isfinite(v)], float)
    return {
        "n": int(len(x)),
        "median": float(np.median(x)) if len(x) else None,
        "q1": float(np.quantile(x, 0.25)) if len(x) else None,
        "q3": float(np.quantile(x, 0.75)) if len(x) else None,
        "minimum": float(np.min(x)) if len(x) else None,
        "maximum": float(np.max(x)) if len(x) else None,
    }
