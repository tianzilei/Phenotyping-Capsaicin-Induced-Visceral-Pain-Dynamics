"""Diagnostic candidate detectors; output is not adjudicated ECG R peaks."""

import numpy as np
from scipy import signal


def detect_multilead(ecg_leads, fs, cfg):
    """Detect ECG candidates from three synchronized leads using spatial energy.

    This is a transparent candidate detector for review. It does not create
    adjudicated R/NN labels and rejects nonfinite input rather than filling it.
    """
    x = np.asarray(ecg_leads, dtype=float)
    if x.ndim != 2 or x.shape[0] != 3 or x.shape[1] < int(3 * fs):
        raise ValueError(
            "Three synchronized ECG leads and sufficient duration required"
        )
    if not np.isfinite(x).all():
        raise ValueError("Finite ECG group required; missing samples are not filled")
    low, high = (
        float(cfg["detection_filter"]["low_hz"]),
        float(cfg["detection_filter"]["high_hz"]),
    )
    sos = signal.butter(
        int(cfg["detection_filter"]["order"]),
        [low, high],
        btype="bandpass",
        fs=fs,
        output="sos",
    )
    filtered = signal.sosfiltfilt(sos, x, axis=1)
    vx, vy, vz = (
        filtered[0],
        (2 / np.sqrt(3)) * filtered[1] - (1 / np.sqrt(3)) * filtered[0],
        filtered[2],
    )
    spatial_velocity = np.sqrt(sum(np.gradient(v, 1 / fs) ** 2 for v in (vx, vy, vz)))
    energy = spatial_velocity**2
    short = max(1, int(round(float(cfg["energy_smoothing_seconds"]) * fs)))
    background = max(short + 1, int(round(float(cfg["background_seconds"]) * fs)))
    envelope = np.convolve(energy, np.ones(short) / short, mode="same")
    baseline = np.convolve(envelope, np.ones(background) / background, mode="same")
    initial = max(1, int(round(float(cfg["initialization_seconds"]) * fs)))
    initial_values = envelope[:initial]
    noise = float(np.median(initial_values))
    signal_level = float(np.percentile(initial_values, 95))
    if not np.isfinite(signal_level) or signal_level <= noise:
        signal_level = noise + max(np.finfo(float).eps, float(np.std(initial_values)))
    alpha = float(cfg["threshold_update_alpha"])
    refractory = max(1, int(round(float(cfg["refractory_seconds"]) * fs)))
    peaks, _ = signal.find_peaks(envelope, distance=refractory)
    accepted = []
    last = -refractory
    for peak in peaks:
        value = float(envelope[peak])
        threshold = noise + 0.5 * (signal_level - noise)
        if value >= threshold and peak - last >= refractory:
            accepted.append(int(peak))
            signal_level = alpha * signal_level + (1 - alpha) * value
            last = int(peak)
        else:
            noise = alpha * noise + (1 - alpha) * value
    # Search-back over long gaps using the protocol's reduced threshold.
    searchback = float(cfg["searchback_factor"])
    reduced = float(cfg["searchback_threshold_fraction"])
    if accepted:
        additions = []
        typical = float(np.median(np.diff(accepted))) if len(accepted) > 1 else fs
        for left, right in zip(accepted[:-1], accepted[1:]):
            if right - left <= searchback * typical:
                continue
            candidates = peaks[
                (peaks > left + refractory) & (peaks < right - refractory)
            ]
            if len(candidates):
                candidate = int(candidates[np.argmax(envelope[candidates])])
                if envelope[candidate] >= noise + reduced * (signal_level - noise):
                    additions.append(candidate)
        accepted = sorted(set(accepted + additions))
    radius = max(1, int(round(float(cfg["refine_radius_seconds"]) * fs)))
    refined = []
    support = []
    for peak in accepted:
        lo, hi = max(0, peak - radius), min(x.shape[1], peak + radius + 1)
        local = np.argmax(np.abs(x[:, lo:hi]), axis=1) + lo
        refined.append(int(round(float(np.median(local)))))
        support.append(
            int(
                np.sum(
                    np.ptp(
                        x[
                            :,
                            max(0, peak - radius) : min(x.shape[1], peak + radius + 1),
                        ],
                        axis=1,
                    )
                    > 0
                )
            )
        )
    refined = np.asarray(refined, dtype=int)
    if len(refined):
        keep = np.r_[True, np.diff(refined) >= refractory]
        refined = refined[keep]
        support = [value for value, flag in zip(support, keep) if flag]
    return dict(
        status="multilead_candidates_not_adjudicated",
        peaks=refined,
        support=np.asarray(support, dtype=int),
        filtered=filtered,
        envelope=envelope,
        baseline=baseline,
        spatial_velocity=spatial_velocity,
    )


def match_candidates(a, b, tolerance):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if (
        tolerance < 0
        or not np.isfinite(a).all()
        or not np.isfinite(b).all()
        or np.any(np.diff(a) <= 0)
        or np.any(np.diff(b) <= 0)
    ):
        raise ValueError(
            "Strictly increasing finite event times and nonnegative tolerance required"
        )
    i = j = 0
    matches = []
    while i < len(a) and j < len(b):
        if abs(a[i] - b[j]) <= tolerance + 1e-12:
            matches.append((i, j))
            i += 1
            j += 1
        elif a[i] < b[j]:
            i += 1
        else:
            j += 1
    return matches


def enforce_distance(indices, scores, distance):
    indices = np.unique(indices).astype(int)
    # Larger score first, earlier location breaks a tie. No invented gap repair.
    order = sorted(indices, key=lambda i: (-scores[i], i))
    occupied = np.zeros(len(scores), dtype=bool)
    kept = []
    for i in order:
        if not occupied[i]:
            kept.append(i)
            occupied[max(0, i - distance + 1) : min(len(scores), i + distance)] = True
    return np.array(sorted(kept), dtype=int)


def detect_candidates(x, rate, cfg):
    x = np.asarray(x, dtype=float)
    if x.ndim != 1 or not np.isfinite(x).all():
        raise ValueError(
            "Finite one-dimensional signal required; missing samples are not filled"
        )
    trim = int(cfg["edge_trim_seconds"] * rate)
    if len(x) <= 2 * trim + rate:
        raise ValueError("Insufficient signal after trimming")
    empty = np.array([], dtype=int)
    if np.all(x == x[0]):
        return dict(
            status="constant_no_candidates",
            amplitude=empty,
            energy=empty,
            filtered=np.zeros(len(x) - 2 * trim),
            offset_samples=trim,
        )
    sos = signal.butter(
        cfg["butterworth_order"],
        cfg["filter_hz"],
        btype="bandpass",
        fs=rate,
        output="sos",
    )
    y = signal.sosfiltfilt(sos, x)
    y = y[trim:-trim] if trim else y
    amplitude = np.abs(y)
    width = max(1, int(round(cfg["energy_smoothing_seconds"] * rate)))
    energy = np.convolve(
        np.gradient(y) * np.gradient(y), np.ones(width) / width, mode="same"
    )
    block = int(cfg["threshold_block_seconds"] * rate)
    amp_candidates = []
    energy_candidates = []
    distance = int(round(cfg["minimum_distance_seconds"] * rate))
    if distance < 1:
        raise ValueError("Minimum distance must be positive")
    # Detect globally so block boundaries do not suppress an actual local maximum.
    ai, props = signal.find_peaks(amplitude, prominence=0)
    ei, _ = signal.find_peaks(energy)
    for start in range(0, len(y), block):
        stop = min(start + block, len(y))
        a = amplitude[start:stop]
        e = energy[start:stop]
        am = float(np.median(np.abs(a - np.median(a))))
        em = float(np.median(np.abs(e - np.median(e))))
        mask = (
            (ai >= start)
            & (ai < stop)
            & (props["prominences"] >= cfg["amplitude_prominence_mad_multiplier"] * am)
        )
        amp_candidates.extend(ai[mask])
        mask = (
            (ei >= start)
            & (ei < stop)
            & (energy[ei] > np.median(e) + cfg["energy_threshold_mad_multiplier"] * em)
        )
        energy_candidates.extend(ei[mask])
    ai = enforce_distance(amp_candidates, amplitude, distance)
    ei = enforce_distance(energy_candidates, energy, distance)
    radius = int(round(cfg["energy_refinement_seconds_each_side"] * rate))
    refined = []
    for i in ei:
        lo = max(0, i - radius)
        hi = min(len(y), i + radius + 1)
        refined.append(lo + int(np.argmax(amplitude[lo:hi])))
    ei = enforce_distance(refined, amplitude, distance)
    return dict(
        status="candidates_not_adjudicated",
        amplitude=ai,
        energy=ei,
        filtered=y,
        offset_samples=trim,
    )


def detect_candidates_from_filtered(y, rate, cfg):
    """Apply the frozen threshold logic to an already filtered/truncated signal."""
    y = np.asarray(y, dtype=float)
    if y.ndim != 1 or not np.isfinite(y).all() or len(y) < rate:
        raise ValueError("Finite filtered signal required")
    amplitude = np.abs(y)
    width = max(1, int(round(cfg["energy_smoothing_seconds"] * rate)))
    energy = np.convolve(
        np.gradient(y) * np.gradient(y), np.ones(width) / width, mode="same"
    )
    block = int(cfg["threshold_block_seconds"] * rate)
    distance = int(round(cfg["minimum_distance_seconds"] * rate))
    ai, props = signal.find_peaks(amplitude, prominence=0)
    ei, _ = signal.find_peaks(energy)
    amp_candidates = []
    energy_candidates = []
    for start in range(0, len(y), block):
        stop = min(start + block, len(y))
        a = amplitude[start:stop]
        e = energy[start:stop]
        am = float(np.median(np.abs(a - np.median(a))))
        em = float(np.median(np.abs(e - np.median(e))))
        mask = (
            (ai >= start)
            & (ai < stop)
            & (props["prominences"] >= cfg["amplitude_prominence_mad_multiplier"] * am)
        )
        amp_candidates.extend(ai[mask])
        mask = (
            (ei >= start)
            & (ei < stop)
            & (energy[ei] > np.median(e) + cfg["energy_threshold_mad_multiplier"] * em)
        )
        energy_candidates.extend(ei[mask])
    ai = enforce_distance(amp_candidates, amplitude, distance)
    ei = enforce_distance(energy_candidates, energy, distance)
    radius = int(round(cfg["energy_refinement_seconds_each_side"] * rate))
    refined = []
    for i in ei:
        lo = max(0, i - radius)
        hi = min(len(y), i + radius + 1)
        refined.append(lo + int(np.argmax(amplitude[lo:hi])))
    ei = enforce_distance(refined, amplitude, distance)
    return dict(
        status="candidates_not_adjudicated",
        amplitude=ai,
        energy=ei,
        filtered=y,
        offset_samples=0,
    )


def synthetic_ecg(case, rng, seconds=120, rate=250):
    t = np.arange(int(seconds * rate)) / rate
    if case == "flat":
        return np.zeros(len(t)), np.array([])
    if case == "noise_only":
        return 0.2 * rng.normal(size=len(t)), np.array([])
    times = []
    beat = 0.8
    while beat < seconds - 0.5:
        times.append(beat)
        beat += rng.uniform(0.55, 1.25) if case == "irregular" else 0.8
    times = np.asarray(times)
    y = np.zeros(len(t))
    for b in times:
        y += (
            np.exp(-0.5 * ((t - b) / 0.014) ** 2)
            - 0.15 * np.exp(-0.5 * ((t - b - 0.035) / 0.012) ** 2)
            + 0.2 * np.exp(-0.5 * ((t - b - 0.24) / 0.055) ** 2)
        )
    y += 0.008 * rng.normal(size=len(t))
    if case == "inverted":
        y = -y
    if case == "baseline_and_line":
        y += 0.6 * np.sin(2 * np.pi * 0.2 * t) + 0.12 * np.sin(2 * np.pi * 50 * t)
    if case == "motion_burst":
        mask = (t >= 45) & (t < 55)
        y[mask] += 1.5 * rng.normal(size=sum(mask))
        y += 2 * (t >= 70)
    return y, times
