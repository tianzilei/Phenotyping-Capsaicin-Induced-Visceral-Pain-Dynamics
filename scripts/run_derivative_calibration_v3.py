"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wilson(k, n):
    p = k / n
    z = 1.959963984540054
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (center - half, center + half)
