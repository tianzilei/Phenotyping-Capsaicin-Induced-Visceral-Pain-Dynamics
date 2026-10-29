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
    m2 = re.search("date_created_utc: (\\d{4}-\\d\\d-\\d\\dT[^ ]+)", s)
    return datetime.fromisoformat(m2.group(1)) if m2 else None


def reg(y, x, subjects=None, windows=None):
    """Subject- and window-adjusted association; no pooled repeated-window estimate."""
    y = np.asarray(y, float)
    x = np.asarray(x, float)
    if len(y) == 0:
        return (None, None)
    if subjects is None:
        subjects = ["all"] * len(y)
    if windows is None:
        windows = ["all"] * len(y)
    levels = [["intercept"], sorted(set(subjects))[1:], sorted(set(windows))[1:]]
    cols = [np.ones(len(y))]
    for vals in levels[1:]:
        for v in vals:
            cols.append(
                np.array(
                    [
                        1.0 if z == v else 0.0
                        for z in (subjects if vals is levels[1] else windows)
                    ]
                )
            )
    Z = np.column_stack(cols)
    try:
        rx = y - Z @ np.linalg.lstsq(Z, y, rcond=None)[0]
        qx = x - Z @ np.linalg.lstsq(Z, x, rcond=None)[0]
    except np.linalg.LinAlgError:
        return (None, None)
    den = float(qx @ qx)
    return (
        float(qx @ rx / den) if den > 1e-12 else None,
        float(np.corrcoef(rx, qx)[0, 1])
        if den > 1e-12 and np.std(rx) > 0 and (np.std(qx) > 0)
        else None,
    )


def bootstrap(rows, xkey, seed=20260919, B=2000):
    rng = np.random.default_rng(seed)
    ids = sorted({r["subject_id"] for r in rows})
    vals = []
    for _ in range(B):
        take = rng.choice(ids, size=len(ids), replace=True)
        sample = []
        for i in take:
            sample.extend((r for r in rows if r["subject_id"] == i))
        b, c = reg(
            [r["vas_mean"] for r in sample],
            [r[xkey] for r in sample],
            [r["subject_id"] for r in sample],
            [r["window_index"] for r in sample],
        )
        if b is not None:
            vals.append(b)
    return dict(
        n_bootstrap=len(vals),
        beta_low=float(np.quantile(vals, 0.025)) if vals else None,
        beta_median=float(np.median(vals)) if vals else None,
        beta_high=float(np.quantile(vals, 0.975)) if vals else None,
    )
