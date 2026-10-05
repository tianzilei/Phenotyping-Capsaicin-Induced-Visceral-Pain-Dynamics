"""Development-only signal diagnostics; none of these scores are reference accuracy."""

from __future__ import annotations

import numpy as np
from scipy import signal


def event_clusters(lead_peaks, fs: float, tolerance_seconds: float = 0.03):
    """Group detections by total cluster span, with at most one vote per lead."""
    items = sorted(
        (int(p), lead) for lead, peaks in enumerate(lead_peaks) for p in peaks
    )
    span = max(0, round(tolerance_seconds * fs))
    groups = []
    for item in items:
        if not groups or item[0] - groups[-1][0][0] > span:
            groups.append([item])
        else:
            groups[-1].append(item)
    result = []
    for group in groups:
        by_lead = {}
        center = float(np.median([p for p, _ in group]))
        for lead in {lead for _, lead in group}:
            candidates = [p for p, other in group if other == lead]
            by_lead[lead] = min(candidates, key=lambda p: (abs(p - center), p))
        result.append((int(round(np.median(list(by_lead.values())))), len(by_lead)))
    return result


def coincidence_diagnostic(
    lead_peaks,
    fs: float,
    n_samples: int,
    seed: int = 20260929,
    replicates: int = 16,
    minimum_shift_seconds: float = 2.0,
    maximum_shift_seconds: float = 10.0,
):
    """Symmetrically shift peak trains and compare rates on one common core."""
    duration = n_samples / fs
    max_shift = min(maximum_shift_seconds, duration / 4)
    if (
        len(lead_peaks) < 2
        or duration <= 2 * max_shift
        or replicates < 1
        or minimum_shift_seconds <= 0
        or max_shift < minimum_shift_seconds
    ):
        return None
    rng = np.random.default_rng(seed)
    guard = int(np.ceil(max_shift * fs))
    core_start, core_end = guard, n_samples - guard
    core_minutes = (core_end - core_start) / fs / 60
    observed = [np.asarray(peaks, dtype=int) for peaks in lead_peaks]
    observed_clusters = event_clusters(observed, fs)
    observed_count = sum(
        votes >= 2 and core_start <= time < core_end
        for time, votes in observed_clusters
    )
    rates = []
    for _ in range(replicates):
        shifted = [np.asarray(lead_peaks[0], dtype=int)]
        for peaks in lead_peaks[1:]:
            magnitude = rng.uniform(minimum_shift_seconds, max_shift)
            offset = int(round(magnitude * fs)) * (-1 if rng.random() < 0.5 else 1)
            moved = np.asarray(peaks, dtype=int) + offset
            shifted.append(moved[(moved >= 0) & (moved < n_samples)])
        count = sum(
            votes >= 2 and core_start <= time < core_end
            for time, votes in event_clusters(shifted, fs)
        )
        rates.append(count / core_minutes)
    observed_rate = observed_count / core_minutes
    median = float(np.median(rates))
    return {
        "coincidence_core_seconds": float((core_end - core_start) / fs),
        "observed_multilead_events_core": int(observed_count),
        "observed_multilead_rate_per_minute": float(observed_rate),
        "shift_coincidence_rate_median_per_minute": median,
        "shift_coincidence_rate_max_per_minute": float(max(rates)),
        "observed_to_shift_median_rate_ratio": float(observed_rate / median)
        if median > 0
        else None,
        "shift_replicates": replicates,
        "shift_semantics": "chance_alignment_sensitivity_not_false_positive_rate",
    }


def align_candidate(
    energy_sample: int, filtered_lead, fs: float, radius_seconds: float = 0.08
) -> int:
    """Localize a QRS extremum near the energy candidate, without a truth claim."""
    y = np.asarray(filtered_lead)
    radius = max(1, round(radius_seconds * fs))
    start = max(0, energy_sample - radius)
    end = min(len(y), energy_sample + radius + 1)
    if start >= end:
        raise ValueError("candidate outside waveform")
    return int(start + np.argmax(np.abs(y[start:end])))


def continuous_runs(mask, min_samples: int = 1):
    padded = np.pad(np.asarray(mask, dtype=bool), (1, 1))
    starts = np.flatnonzero(np.diff(padded.astype(int)) == 1)
    ends = np.flatnonzero(np.diff(padded.astype(int)) == -1)
    return [(int(a), int(b)) for a, b in zip(starts, ends) if b - a >= min_samples]


def raw_egg_mask(egg, fs: float, flat_seconds: float = 2.0):
    """Conservative hardware-invalid mask; step/motion truth remains unknown."""
    x = np.asarray(egg, dtype=float)
    if x.ndim != 2 or x.shape[0] != 2 or x.shape[1] == 0:
        raise ValueError("expected two nonempty EGG channels")
    valid = np.all(np.isfinite(x), axis=0)
    flat = np.zeros(x.shape[1], dtype=bool)
    for ch in x:
        same = np.r_[
            False, (np.diff(ch) == 0) & np.isfinite(ch[1:]) & np.isfinite(ch[:-1])
        ]
        for a, b in continuous_runs(same, max(1, round(flat_seconds * fs))):
            flat[max(0, a - 1) : b] = True
    return valid & ~flat, {
        "nonfinite_samples": int((~valid).sum()),
        "flatline_samples": int(flat.sum()),
    }


def multitaper_run(egg, fs: float, nw: float = 3.0, tapers: int = 5):
    """Two-channel spectra and coherence estimated across independent tapers."""
    x = signal.detrend(np.asarray(egg, dtype=float), axis=1, type="linear")
    n = x.shape[1]
    if n < 2:
        raise ValueError("short run")
    tap = signal.windows.dpss(n, nw, Kmax=tapers, sym=False)
    fft = np.fft.rfft(x[:, None, :] * tap[None, :, :], axis=-1)
    norm = fs * np.sum(tap**2, axis=1)
    spec = np.abs(fft) ** 2 / norm[None, :, None]
    auto = np.mean(spec, axis=1)
    cross = np.mean(fft[0] * np.conj(fft[1]) / norm[:, None], axis=0)
    coh = np.abs(cross) ** 2 / np.maximum(auto[0] * auto[1], 1e-30)
    return np.fft.rfftfreq(n, 1 / fs), auto.mean(axis=0), np.clip(coh, 0, 1)


def egg_run_metrics(egg, fs: float, slow=(0.033, 0.067), band=(0.008, 0.150)):
    f, power, coherence = multitaper_run(egg, fs)
    base = (f >= band[0]) & (f <= band[1])
    slow_bins = np.flatnonzero((f >= slow[0]) & (f <= slow[1]))
    if base.sum() < 2 or len(slow_bins) < 1:
        raise ValueError("insufficient frequency resolution")
    total_power = float(np.trapezoid(power[base], f[base]))
    slow_power = (
        float(np.trapezoid(power[slow_bins], f[slow_bins]))
        if len(slow_bins) > 1
        else 0.0
    )
    probs = power[base] / max(float(power[base].sum()), 1e-30)
    entropy = float(-np.sum(probs * np.log(probs + 1e-30)) / np.log(len(probs)))
    peak = int(slow_bins[np.argmax(power[slow_bins])])
    return {
        "peak_cpm": float(60 * f[peak]),
        "slow_power": slow_power,
        "total_power": total_power,
        "spectral_entropy": entropy,
        "slow_coherence": float(np.mean(coherence[slow_bins])),
        "bin_width_hz": float(fs / egg.shape[1]),
        "dpss_smoothing_width_hz": float(6 * fs / egg.shape[1]),
    }


def egg_candidate(
    egg,
    fs: float,
    minimum_run_seconds: float = 120,
    minimum_total_seconds: float = 180,
    target_fs: int = 100,
):
    mask, artifacts = raw_egg_mask(egg, fs)
    runs = continuous_runs(mask, max(1, int(np.ceil(minimum_run_seconds * fs))))
    total = sum(b - a for a, b in runs) / fs
    result = {
        **artifacts,
        "valid_run_count": len(runs),
        "valid_seconds": total,
        "max_continuous_seconds": max((b - a for a, b in runs), default=0) / fs,
        "status": "EGG_CANDIDATE_INESTIMABLE",
    }
    if total < minimum_total_seconds:
        return result
    if not np.isclose(fs, round(fs)):
        raise ValueError(
            "noninteger source sampling rate requires separate resampling specification"
        )
    gcd = np.gcd(int(round(fs)), target_fs)
    metrics = []
    weights = []
    for a, b in runs:
        segment = signal.resample_poly(
            np.asarray(egg)[:, a:b], target_fs // gcd, int(round(fs)) // gcd, axis=1
        )
        metrics.append(egg_run_metrics(segment, target_fs))
        weights.append((b - a) / fs)
    weighted = lambda key: float(np.average([m[key] for m in metrics], weights=weights))
    result.update(
        {
            "status": "EGG_CANDIDATE_SPECTRUM_ONLY",
            "peak_cpm_weighted": weighted("peak_cpm"),
            "peak_cpm_min": min(m["peak_cpm"] for m in metrics),
            "peak_cpm_max": max(m["peak_cpm"] for m in metrics),
            "slow_power_ratio": float(
                sum(m["slow_power"] * w for m, w in zip(metrics, weights))
                / max(
                    sum(m["total_power"] * w for m, w in zip(metrics, weights)), 1e-30
                )
            ),
            "spectral_entropy": weighted("spectral_entropy"),
            "slow_coherence_descriptive": weighted("slow_coherence"),
            "coarsest_bin_width_hz": max(m["bin_width_hz"] for m in metrics),
            "widest_dpss_smoothing_hz": max(
                m["dpss_smoothing_width_hz"] for m in metrics
            ),
        }
    )
    return result
