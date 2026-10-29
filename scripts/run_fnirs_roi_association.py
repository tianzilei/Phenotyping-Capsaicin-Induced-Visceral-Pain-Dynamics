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


def beta(rows, key):
    y = np.array([float(r["vas_mean"]) for r in rows])
    x = np.array([float(r[key]) for r in rows])
    s = [r["subject_id"] for r in rows]
    b = [r["block"] for r in rows]
    cols = [np.ones(len(rows))]
    for v in sorted(set(s))[1:]:
        cols.append(np.array([z == v for z in s], float))
    for v in sorted(set(b))[1:]:
        cols.append(np.array([z == v for z in b], float))
    Z = np.column_stack(cols)
    ry = y - Z @ np.linalg.lstsq(Z, y, rcond=None)[0]
    rx = x - Z @ np.linalg.lstsq(Z, x, rcond=None)[0]
    return float(rx @ ry / (rx @ rx)) if rx @ rx > 1e-12 else None


def boot(rows, key, B=2000, seed=20260921):
    rng = np.random.default_rng(seed)
    ids = sorted({r["subject_id"] for r in rows})
    out = []
    for _ in range(B):
        take = rng.choice(ids, len(ids), replace=True)
        s = [r for i in take for r in rows if r["subject_id"] == i]
        v = beta(s, key)
        if v is not None:
            out.append(v)
    return {
        "n_bootstrap": len(out),
        "beta_low": float(np.quantile(out, 0.025)) if out else None,
        "beta_median": float(np.median(out)) if out else None,
        "beta_high": float(np.quantile(out, 0.975)) if out else None,
    }
