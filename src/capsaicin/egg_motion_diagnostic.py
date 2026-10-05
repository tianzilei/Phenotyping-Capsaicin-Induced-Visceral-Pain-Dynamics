"""Conservative EGG derivative-mask diagnostic on uninterrupted ACQ segments."""

from __future__ import annotations

import numpy as np
from scipy import signal

from .electrophysiology_qc_v2 import continuous_runs, egg_run_metrics, raw_egg_mask
from .reanalysis_signals import derivative_flags


def motion_support(
    egg,
    fs: float,
    target_fs: int = 10,
    multiple: float = 8,
    guard_seconds: float = 2,
    reference_seconds: float = 60,
    minimum_run_seconds: float = 120,
    minimum_total_seconds: float = 180,
):
    """Return candidate support and a joint mask, without artifact-truth claims."""
    x = np.asarray(egg, dtype=float)
    if fs <= 0 or not np.isclose(fs, round(fs)):
        raise ValueError("positive integer source sampling rate required")
    if target_fs <= 0 or target_fs > fs:
        raise ValueError("target sampling rate must be positive and <= source rate")
    base_mask, raw_counts = raw_egg_mask(x, fs)
    valid = base_mask.copy()
    motion = np.zeros(x.shape[1], dtype=bool)
    gcd = np.gcd(int(round(fs)), target_fs)
    for a, b in continuous_runs(base_mask):
        if b - a < 3:
            valid[a:b] = False
            continue
        segment = signal.resample_poly(
            x[:, a:b], target_fs // gcd, int(round(fs)) // gcd, axis=1
        )
        coarse_bad = np.zeros(segment.shape[1], dtype=bool)
        for channel in segment:
            coarse_bad |= derivative_flags(
                channel, target_fs, multiple, guard_seconds, reference_seconds
            )
        raw_bins = np.minimum(
            (np.arange(b - a) * target_fs / fs).astype(int), len(coarse_bad) - 1
        )
        motion[a:b] = coarse_bad[raw_bins]
        valid[a:b] &= ~motion[a:b]
    runs = continuous_runs(valid, int(np.ceil(minimum_run_seconds * fs)))
    valid_seconds = sum(b - a for a, b in runs) / fs
    metrics = {
        **raw_counts,
        "motion_candidate_seconds": float(motion.sum() / fs),
        "motion_candidate_fraction": float(motion.mean()),
        "qualifying_runs": len(runs),
        "qualifying_total_seconds": float(valid_seconds),
        "longest_qualifying_seconds": float(
            max((b - a for a, b in runs), default=0) / fs
        ),
        "support_status": "MOTION_SCREENED_CANDIDATE_SUPPORT"
        if valid_seconds >= minimum_total_seconds
        else "MOTION_SCREENED_CANDIDATE_INESTIMABLE",
        "semantic_status": "unvalidated_artifact_proxy_not_physiological_acceptance",
    }
    return metrics, valid


def motion_screened_spectrum(
    egg,
    fs: float,
    valid_mask,
    minimum_run_seconds: float = 120,
    minimum_total_seconds: float = 180,
    target_fs: int = 100,
):
    """Describe only separately resampled, uninterrupted motion-screened runs."""
    x = np.asarray(egg, dtype=float)
    mask = np.asarray(valid_mask, dtype=bool)
    if x.ndim != 2 or x.shape[0] != 2 or mask.shape != (x.shape[1],):
        raise ValueError("mask and two-channel EGG dimensions differ")
    if np.any(mask & ~np.all(np.isfinite(x), axis=0)):
        raise ValueError("valid mask includes nonfinite samples")
    if fs <= 0 or not np.isclose(fs, round(fs)):
        raise ValueError("positive integer source sampling rate required")
    runs = continuous_runs(mask, int(np.ceil(minimum_run_seconds * fs)))
    total = sum(b - a for a, b in runs) / fs
    result = {
        "motion_spectrum_status": "MOTION_SCREENED_SPECTRUM_INESTIMABLE",
        "motion_spectrum_run_count": len(runs),
        "motion_spectrum_used_seconds": float(total),
    }
    if total < minimum_total_seconds:
        return result
    gcd = np.gcd(int(round(fs)), target_fs)
    metrics = []
    weights = []
    for a, b in runs:
        segment = signal.resample_poly(
            x[:, a:b], target_fs // gcd, int(round(fs)) // gcd, axis=1
        )
        metrics.append(egg_run_metrics(segment, target_fs))
        weights.append((b - a) / fs)
    weight_sum = sum(weights)
    result.update(
        {
            "motion_spectrum_status": "MOTION_SCREENED_SPECTRUM_CANDIDATE_ONLY",
            "motion_spectrum_peak_cpm_weighted": float(
                sum(m["peak_cpm"] * w for m, w in zip(metrics, weights)) / weight_sum
            ),
            "motion_spectrum_peak_cpm_min": float(min(m["peak_cpm"] for m in metrics)),
            "motion_spectrum_peak_cpm_max": float(max(m["peak_cpm"] for m in metrics)),
            "motion_spectrum_slow_power_ratio": float(
                sum(m["slow_power"] * w for m, w in zip(metrics, weights))
                / max(
                    sum(m["total_power"] * w for m, w in zip(metrics, weights)), 1e-30
                )
            ),
            "motion_spectrum_entropy": float(
                sum(m["spectral_entropy"] * w for m, w in zip(metrics, weights))
                / weight_sum
            ),
            "motion_spectrum_coherence_descriptive": float(
                sum(m["slow_coherence"] * w for m, w in zip(metrics, weights))
                / weight_sum
            ),
            "motion_spectrum_widest_smoothing_hz": float(
                max(m["dpss_smoothing_width_hz"] for m in metrics)
            ),
        }
    )
    return result
