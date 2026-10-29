"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import numpy as np
from capsaicin.ecg_candidates import match_candidates

ROOT = Path(__file__).resolve().parents[1]


def pairing(a, b, tolerance):
    pairs = match_candidates(a, b, tolerance)
    errors = [abs(a[i] - b[j]) for i, j in pairs]
    return dict(
        matched=len(pairs),
        count_a=len(a),
        count_b=len(b),
        agreement=2 * len(pairs) / (len(a) + len(b)) if len(a) + len(b) else None,
        median_abs_timing_difference_s=float(np.median(errors)) if errors else None,
    )


def intervals_summary(t):
    gaps = np.diff(t)
    return dict(
        candidate_count=len(t),
        interval_count=len(gaps),
        median_interval_s=float(np.median(gaps)) if len(gaps) else None,
        min_interval_s=float(np.min(gaps)) if len(gaps) else None,
        max_interval_s=float(np.max(gaps)) if len(gaps) else None,
    )
