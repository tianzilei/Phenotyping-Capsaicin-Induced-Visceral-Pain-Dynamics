"""Unit-free advisory probes for EGG development diagnostics."""

from __future__ import annotations

import numpy as np
from scipy import signal


def _band_power(f, p, lo, hi):
    mask = (f >= lo) & (f <= hi)
    return float(np.trapezoid(p[mask], f[mask])) if mask.sum() >= 2 else 0.0


def _resample(x, fs: float, target: int):
    if fs <= 0 or not np.isclose(fs, round(fs)) or target <= 0 or target > fs:
        raise ValueError("integer source rate and valid lower target rate required")
    gcd = np.gcd(int(round(fs)), target)
    return signal.resample_poly(
        np.asarray(x, dtype=float), target // gcd, int(round(fs)) // gcd, axis=-1
    )


def unitless_egg_probes(egg, ecg_lead, fs: float, target_fs: int = 20):
    """Compute scale-invariant diagnostics without assigning artifact truth."""
    x = np.asarray(egg, dtype=float)
    ecg = np.asarray(ecg_lead, dtype=float)
    if x.ndim != 2 or x.shape[0] != 2 or ecg.ndim != 1 or x.shape[1] != len(ecg):
        raise ValueError("expected two EGG channels and one aligned ECG lead")
    if not np.isfinite(x).all() or not np.isfinite(ecg).all():
        raise ValueError("probes require a finite uninterrupted record")
    xd = _resample(x, fs, target_fs)
    ed = _resample(ecg, fs, target_fs)
    nper = min(xd.shape[1], max(256, int(120 * target_fs)))
    subslow = []
    repeated = []
    modal_step = []
    for raw_channel, channel in zip(x, xd):
        f, p = signal.welch(
            channel,
            fs=target_fs,
            window="hann",
            nperseg=nper,
            noverlap=nper // 2,
            detrend="linear",
            scaling="density",
        )
        total = _band_power(f, p, 0.005, 0.150)
        subslow.append(_band_power(f, p, 0.005, 1 / 60) / max(total, 1e-30))
        raw_diff = np.diff(raw_channel)
        repeated.append(float(np.mean(raw_diff == 0)))
        diff = raw_diff
        if len(diff):
            scale = float(np.median(np.abs(diff)))
            normalized = diff / max(scale, np.finfo(float).tiny)
            # Quantize only after scale normalization so floating representation
            # does not masquerade as an ADC step pattern.
            _, counts = np.unique(np.round(normalized, 8), return_counts=True)
            modal_step.append(float(counts.max() / len(diff)))
        else:
            modal_step.append(1.0)
    sos = signal.butter(
        4, [8, min(28, fs / 2 - 1)], btype="bandpass", fs=fs, output="sos"
    )
    filtered = signal.sosfiltfilt(sos, ecg)
    envelope = np.convolve(
        np.gradient(filtered) ** 2,
        np.ones(max(1, round(0.12 * fs))) / max(1, round(0.12 * fs)),
        mode="same",
    )
    mad = 1.4826 * np.median(np.abs(envelope - np.median(envelope)))
    peaks, _ = signal.find_peaks(
        envelope,
        distance=max(1, round(0.2 * fs)),
        prominence=max(2 * mad, np.finfo(float).eps),
    )
    rr = np.diff(peaks) / fs
    rr = rr[(rr >= 0.3) & (rr <= 1.8)]
    heart_hz = float(1 / np.median(rr)) if len(rr) else np.nan
    coherence = []
    for channel in xd:
        f, c = signal.coherence(
            ed,
            channel,
            fs=target_fs,
            nperseg=min(len(ed), max(256, int(30 * target_fs))),
        )
        if np.isfinite(heart_hz):
            bands = []
            for harmonic in (1, 2):
                center = harmonic * heart_hz
                mask = (f >= center - 0.05) & (f <= center + 0.05)
                if np.any(mask):
                    bands.append(float(np.nanmax(c[mask])))
            coherence.append(max(bands) if bands else np.nan)
        else:
            coherence.append(np.nan)
    return {
        "subslow_ratio_ch1": subslow[0],
        "subslow_ratio_ch2": subslow[1],
        "subslow_ratio_max": max(subslow),
        "exact_repeat_fraction_max": max(repeated),
        "modal_difference_fraction_max": max(modal_step),
        "candidate_heart_rate_hz": heart_hz,
        "ecg_egg_harmonic_coherence_ch1": coherence[0],
        "ecg_egg_harmonic_coherence_ch2": coherence[1],
        "ecg_egg_harmonic_coherence_max": float(np.nanmax(coherence))
        if np.any(np.isfinite(coherence))
        else np.nan,
        "harmonic_probe_in_egg_analysis_band": bool(
            np.isfinite(heart_hz) and heart_hz <= 0.150
        ),
        "repeat_probe_interpretation": "raw_quantization_or_oversampling_descriptor_not_dropout_evidence",
        "harmonic_probe_interpretation": "high_frequency_leakage_descriptor_not_slow_band_contamination_proof",
        "semantic_status": "unitless_advisory_probe_not_artifact_or_crosstalk_acceptance",
    }
