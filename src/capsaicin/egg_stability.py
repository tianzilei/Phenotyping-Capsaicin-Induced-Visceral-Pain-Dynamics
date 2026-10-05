"""Within-recording EGG spectrum stability utilities."""

from __future__ import annotations
import numpy as np
from scipy import stats
from .electrophysiology_qc_v2 import egg_run_metrics, multitaper_run


def fixed_segment(egg, fs, start_seconds, length_seconds, target_fs=100):
    a = round(start_seconds * fs)
    b = a + round(length_seconds * fs)
    if a < 0 or b > egg.shape[1]:
        raise ValueError("segment outside recording")
    from scipy import signal

    gcd = np.gcd(int(round(fs)), target_fs)
    return signal.resample_poly(
        np.asarray(egg)[:, a:b], target_fs // gcd, int(round(fs)) // gcd, axis=1
    )


def spectrum_distance(first, second, fs):
    f1, p1, _ = multitaper_run(first, fs)
    f2, p2, _ = multitaper_run(second, fs)
    mask1 = (f1 >= 0.008) & (f1 <= 0.150)
    mask2 = (f2 >= 0.008) & (f2 <= 0.150)
    grid = np.linspace(
        max(f1[mask1][0], f2[mask2][0]), min(f1[mask1][-1], f2[mask2][-1]), 256
    )
    a = np.interp(grid, f1[mask1], p1[mask1])
    b = np.interp(grid, f2[mask2], p2[mask2])
    corr = float(np.corrcoef(a, b)[0, 1]) if np.std(a) > 0 and np.std(b) > 0 else None
    wd = float(
        stats.wasserstein_distance(
            f1[mask1], f2[mask2], u_weights=p1[mask1], v_weights=p2[mask2]
        )
    )
    return corr, wd


def segment_metrics(segment, fs=100):
    return egg_run_metrics(segment, fs)
