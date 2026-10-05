"""Frozen, non-destructive ECG-to-EGG calibration primitives.

These functions operate on arrays supplied by a caller and never blank,
interpolate, or join gaps.  They are deliberately small so a run can record
the exact frozen parameters and the calibration/assessment split.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy import signal


@dataclass(frozen=True)
class CalibrationSpec:
    sampling_hz: float = 100.0
    train_seconds: float = 120.0
    guard_seconds: float = 10.0
    validation_seconds: float = 120.0
    window_seconds: tuple[float, float] = (-0.100, 0.150)
    correlation_min: float = 0.5
    alpha_min: float = 0.5
    alpha_max: float = 1.5
    exploratory_attenuation_db: float = 6.0
    legacy_attenuation_db: float = 15.0
    slow_fidelity_rmse_fraction: float = 0.03
    slow_fidelity_phase_rad: float = 0.05
    null_leakage_db: float = -60.0


def session_slices(
    n_samples: int, fs: float, spec: CalibrationSpec = CalibrationSpec()
):
    """Return independent train/guard/validation slices, or raise if short."""
    train = int(round(spec.train_seconds * fs))
    guard = int(round(spec.guard_seconds * fs))
    val = int(round(spec.validation_seconds * fs))
    if n_samples < train + guard + val:
        raise ValueError("rest_session_short_for_frozen_calibration")
    return (
        slice(0, train),
        slice(train, train + guard),
        slice(train + guard, train + guard + val),
    )


def _window_indices(peaks: np.ndarray, fs: float, bounds: tuple[float, float], n: int):
    left, right = round(bounds[0] * fs), round(bounds[1] * fs)
    for p in np.asarray(peaks, dtype=int):
        a, b = int(p + left), int(p + right)
        if a >= 0 and b <= n and b > a:
            yield a, b


def estimate_template(
    egg: np.ndarray,
    r_peaks: np.ndarray,
    fs: float,
    spec: CalibrationSpec = CalibrationSpec(),
):
    """Estimate one template per EGG channel from the calibration segment."""
    x = np.asarray(egg, dtype=float)
    if x.ndim == 1:
        x = x[None, :]
    pieces = [[] for _ in range(x.shape[0])]
    for a, b in _window_indices(r_peaks, fs, spec.window_seconds, x.shape[1]):
        t = np.linspace(-1.0, 1.0, b - a)
        taper = signal.windows.tukey(b - a, alpha=0.2)
        for ch in range(x.shape[0]):
            y = x[ch, a:b]
            if not np.all(np.isfinite(y)):
                continue
            y = signal.detrend(y, type="linear") * taper
            pieces[ch].append(y)
    if any(not p for p in pieces):
        raise ValueError("insufficient_finite_qrs_windows_for_template")
    # Robust event average; normalize only for the projection formula.
    templates = np.vstack([np.median(np.asarray(p), axis=0) for p in pieces])
    norms = np.linalg.norm(templates, axis=1)
    if np.any(norms <= np.finfo(float).eps):
        raise ValueError("degenerate_crosstalk_template")
    return templates


def subtract_frozen_template(
    egg: np.ndarray,
    r_peaks: np.ndarray,
    template: np.ndarray,
    fs: float,
    spec: CalibrationSpec = CalibrationSpec(),
):
    """Apply event-local subtraction without changing length or creating gaps."""
    raw = np.asarray(egg, dtype=float)
    one = raw.ndim == 1
    out = raw[None, :].copy() if one else raw.copy()
    temp = np.asarray(template, dtype=float)
    if temp.ndim == 1:
        temp = temp[None, :]
    if temp.shape[0] != out.shape[0]:
        raise ValueError("template_channel_count_mismatch")
    applied = 0
    for a, b in _window_indices(r_peaks, fs, spec.window_seconds, out.shape[1]):
        for ch in range(out.shape[0]):
            y = out[ch, a:b]
            t = temp[ch]
            if not np.all(np.isfinite(y)):
                continue
            yc, tc = y - np.mean(y), t - np.mean(t)
            denom = float(np.dot(tc, tc))
            if denom <= np.finfo(float).eps:
                continue
            corr = float(np.corrcoef(yc, tc)[0, 1]) if np.std(yc) > 0 else 0.0
            alpha = float(np.dot(yc, tc) / denom)
            if corr >= spec.correlation_min and alpha > 0:
                out[ch, a:b] = (
                    y - float(np.clip(alpha, spec.alpha_min, spec.alpha_max)) * t
                )
                applied += 1
    return out[0] if one else out, {
        "applied_windows": applied,
        "input_length": int(out.shape[1]),
    }


def classify_attenuation(attenuation_db: float, fidelity_ok: bool):
    """Keep exploratory 6 dB and legacy 15 dB decisions separate."""
    return {
        "attenuation_db": float(attenuation_db),
        "pass_6db_exploratory": bool(fidelity_ok and attenuation_db >= 6.0),
        "pass_15db_legacy": bool(fidelity_ok and attenuation_db >= 15.0),
        "status": "E05_EXPLORATORY_PASSED"
        if fidelity_ok and attenuation_db >= 6.0
        else "E05_UNRESOLVED",
    }
