"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def time_segments(t):
    if len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError("Invalid actual Hb time")
    dt = float(np.median(np.diff(t)))
    cuts = np.r_[0, np.flatnonzero(np.diff(t) > 1.5 * dt) + 1, len(t)]
    return ([(float(t[a]), float(t[b - 1])) for a, b in zip(cuts[:-1], cuts[1:])], dt)


def available(intervals, a, b):
    return any((x <= a + 1e-09 and y >= b - 1e-09 for x, y in intervals))


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


def bound(n):
    return 1 - 0.05 ** (1 / n) if n else None
