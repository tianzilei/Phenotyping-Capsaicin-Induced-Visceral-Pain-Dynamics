"""Numeric waveform descriptors, without physiological acceptance thresholds."""

import numpy as np


def describe(values, rate):
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or not len(x) or not np.isfinite(rate) or rate <= 0:
        raise ValueError("Nonempty vector and positive finite rate required")
    good = np.isfinite(x)
    same = good[1:] & good[:-1] & (x[1:] == x[:-1])
    breaks = np.flatnonzero(~same) + 1
    boundaries = np.r_[0, breaks, len(x)]
    longest = int(np.max(np.diff(boundaries))) if good.any() else 0
    valid = x[good]
    return dict(
        n_samples=len(x),
        nonfinite=int((~good).sum()),
        min_native=float(valid.min()) if len(valid) else None,
        max_native=float(valid.max()) if len(valid) else None,
        sd_native=float(valid.std()) if len(valid) else None,
        zero_fraction=float(np.mean(valid == 0)) if len(valid) else None,
        equal_adjacent_pairs=int(same.sum()),
        longest_constant_samples=longest,
        longest_constant_span_s=max(0, longest - 1) / rate,
        whole_constant=bool(good.all() and np.all(x == x[0])),
    )


def agreement(raw, exported, stride, offset, tolerance):
    a = np.asarray(raw)[offset::stride]
    b = np.asarray(exported)
    if (
        a.shape != b.shape
        or not a.size
        or not np.isfinite(a).all()
        or not np.isfinite(b).all()
    ):
        return dict(eligible=False, matches=False, max_abs_difference=None)
    error = float(np.max(np.abs(a - b)))
    return dict(eligible=True, matches=error <= tolerance, max_abs_difference=error)
