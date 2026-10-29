"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def write(p, rows):
    if not rows:
        return
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def scalar(group, name):
    if name not in group:
        return ""
    v = group[name][()]
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    if isinstance(v, np.ndarray):
        return str(v.tolist())
    return str(v)
