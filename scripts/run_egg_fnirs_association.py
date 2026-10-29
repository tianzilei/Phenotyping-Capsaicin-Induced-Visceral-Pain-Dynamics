"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def read(p):
    with Path(p).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(p, rows):
    keys = list(dict.fromkeys((k for r in rows for k in r)))
    with Path(p).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def beta(rows, xkey, ykey):
    y = np.array([float(r[ykey]) for r in rows])
    x = np.array([float(r[xkey]) for r in rows])
    s = [r["subject_id"] for r in rows]
    b = [r["block"] for r in rows]

    def resid(v):
        z = v - v.mean()
        for _ in range(4):
            for g in (s, b):
                means = {
                    k: float(np.mean([z[i] for i, q in enumerate(g) if q == k]))
                    for k in set(g)
                }
                z = np.array([z[i] - means[q] for i, q in enumerate(g)])
            z -= z.mean()
        return z

    ry = resid(y)
    rx = resid(x)
    return float(rx @ ry / (rx @ rx)) if rx @ rx > 1e-12 else None
