"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import numpy as np
from scipy import signal
from run_rest_waveform_qc import channel_indices, downsample

ROOT = Path(__file__).resolve().parents[1]
MIN_RUN = 120.0
MIN_TOTAL = 180.0
QUALITY_MIN = 0.65
SLOW = (0.033, 0.067)
BAND = (0.008, 0.15)


def longest_runs(mask: np.ndarray, fs: float, minimum: float):
    runs, start = ([], None)
    for i, ok in enumerate(np.asarray(mask, dtype=bool)):
        if ok and start is None:
            start = i
        if (not ok or i == len(mask) - 1) and start is not None:
            end = i if ok and i == len(mask) - 1 else i
            if (end - start) / fs >= minimum:
                runs.append((start, end))
            start = None
    return runs


def quality_mask(x: np.ndarray, fs: float) -> np.ndarray:
    return np.all(np.isfinite(np.asarray(x, dtype=float)), axis=0)


def multitaper_psd(x: np.ndarray, fs: float):
    n = len(x)
    tapers = signal.windows.dpss(n, NW=3.0, Kmax=5, sym=False)
    y = signal.detrend(np.asarray(x, dtype=float), type="linear")
    spectra = []
    for taper in tapers:
        z = np.fft.rfft(y * taper)
        spectra.append(np.abs(z) ** 2 / (fs * np.sum(taper * taper)))
    return (np.fft.rfftfreq(n, 1 / fs), np.mean(spectra, axis=0))


def band_integral(f, p, lo, hi):
    m = (f >= lo) & (f <= hi)
    return float(np.trapezoid(p[m], f[m])) if np.any(m) else 0.0


def spectrum_metrics(x: np.ndarray, fs: float, runs):
    pooled = None
    weights = []
    used = []
    for a, b in runs:
        spectra = []
        for ch in range(2):
            f, p = multitaper_psd(x[ch, a:b], fs)
            spectra.append(p)
        p = np.mean(spectra, axis=0)
        pooled = p * (b - a) if pooled is None else pooled + p * (b - a)
        weights.append(b - a)
        used.append((f, p, a, b))
    if pooled is None:
        return {}
    pooled = pooled / max(sum(weights), 1)
    base = band_integral(f, pooled, *BAND)
    slow = band_integral(f, pooled, *SLOW)
    band = (f >= BAND[0]) & (f <= BAND[1])
    probs = pooled[band].clip(min=0)
    probs = probs / probs.sum() if probs.sum() > 0 else probs
    entropy = (
        float(-np.sum(probs * np.log(probs + 1e-15)) / np.log(len(probs)))
        if len(probs) > 1 and probs.sum() > 0
        else np.nan
    )
    slow_idx = np.flatnonzero((f >= SLOW[0]) & (f <= SLOW[1]))
    peak = (
        float(f[slow_idx[np.argmax(pooled[slow_idx])]] * 60.0)
        if len(slow_idx)
        else np.nan
    )
    return {
        "dominant_freq_cpm": peak,
        "slow_power_ratio": float(slow / max(base, 1e-20)),
        "spectral_entropy": entropy,
        "frequency_resolution_hz": float(1.0 / max(weights) * fs),
    }


def coherence_score(x: np.ndarray, fs: float, runs):
    vals = []
    for a, b in runs:
        f, c = signal.coherence(
            x[0, a:b], x[1, a:b], fs=fs, nperseg=min(b - a, int(120 * fs))
        )
        m = (f >= SLOW[0]) & (f <= SLOW[1])
        if np.any(m) and np.any(np.isfinite(c[m])):
            vals.append(float(np.nanmax(c[m])))
    return float(np.average(vals, weights=[b - a for a, b in runs])) if vals else 0.0


def analyze_record(arr, fs, names, stage):
    _, egg_idx = channel_indices(names)
    x, fs = downsample(arr[egg_idx], fs, 100)
    mask = quality_mask(x, fs)
    runs = longest_runs(mask, fs, MIN_RUN)
    total = sum((b - a for a, b in runs)) / fs
    longest = max((b - a for a, b in runs), default=0) / fs
    total_record = x.shape[1] / fs
    coverage = min(total / max(total_record, 1e-12), 1.0)
    continuity = min(longest / max(total_record, 1e-12), 1.0)
    agreement = coherence_score(x, fs, runs)
    aqs = 0.4 * coverage + 0.3 * continuity + 0.3 * agreement
    metrics = (
        spectrum_metrics(x, fs, runs)
        if longest >= MIN_RUN and total >= MIN_TOTAL and (aqs >= QUALITY_MIN)
        else {}
    )
    alt = "E08_ALT_ESTIMATED" if metrics else "E08_ALT_INESTIMABLE"
    legacy = (
        "LEGACY_DUAL_256S_AVAILABLE" if longest >= 384.0 else "STRUCTURALLY_UNFULFILLED"
    )
    return {
        "stage": stage,
        "record_seconds": total_record,
        "valid_runs_count": len(runs),
        "total_valid_seconds": total,
        "max_continuous_seconds": longest,
        "q_coverage": coverage,
        "q_continuity": continuity,
        "q_channel_agreement": agreement,
        "aqs_egg": aqs,
        "e08_legacy_dual_256s_status": legacy,
        "e08_alt_status": alt,
        **metrics,
    }
