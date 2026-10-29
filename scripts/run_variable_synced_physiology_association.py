"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
import re
from datetime import datetime
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


def parse_expstart(s):
    return datetime.strptime(s.strip(), "%Y-%m-%d %Hh%M.%S.%f %z")


def parse_marker(s):
    m = re.search("date_created_utc: (\\d{4}-\\d\\d-\\d\\dT[^ ]+)", s)
    return datetime.fromisoformat(m.group(1)) if m else None


def reg(y, x, subjects, windows):
    y = np.asarray(y, float)
    x = np.asarray(x, float)
    cols = [np.ones(len(y))]
    for v in sorted(set(subjects))[1:]:
        cols.append(np.array([z == v for z in subjects], float))
    for v in sorted(set(windows))[1:]:
        cols.append(np.array([z == v for z in windows], float))
    Z = np.column_stack(cols)
    ry = y - Z @ np.linalg.lstsq(Z, y, rcond=None)[0]
    rx = x - Z @ np.linalg.lstsq(Z, x, rcond=None)[0]
    return float(rx @ ry / (rx @ rx)) if rx @ rx > 1e-12 else None


def bootstrap(rows, key, B=2000, seed=20260921):
    rng = np.random.default_rng(seed)
    ids = sorted({r["subject_id"] for r in rows})
    vals = []
    for _ in range(B):
        take = rng.choice(ids, len(ids), replace=True)
        s = [r for i in take for r in rows if r["subject_id"] == i]
        b = reg(
            [r["vas_mean"] for r in s],
            [r[key] for r in s],
            [r["subject_id"] for r in s],
            [r["window_index"] for r in s],
        )
        if b is not None:
            vals.append(b)
    return {
        "n_bootstrap": len(vals),
        "beta_low": float(np.quantile(vals, 0.025)) if vals else None,
        "beta_median": float(np.median(vals)) if vals else None,
        "beta_high": float(np.quantile(vals, 0.975)) if vals else None,
    }
