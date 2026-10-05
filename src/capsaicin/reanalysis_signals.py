"""Transparent candidate signal checks; no independently validated accept labels."""

import numpy as np
from scipy import signal, ndimage
from .reanalysis import time_weights


def derivative_flags(x, fs, multiple=8, guard=2, reference_seconds=60):
    x = np.asarray(x, float)
    n = len(x)
    bad = ~np.isfinite(x)
    if n < 3:
        return np.ones(n, bool)
    # Candidate local robust reference; coarse evaluation avoids quadratic rolling MAD.
    d = np.r_[0, np.diff(x)] * fs
    step = max(1, int(10 * fs))
    half = int(reference_seconds * fs / 2)
    for start in range(0, n, step):
        ref = d[max(0, start - half) : min(n, start + step + half)]
        ref = ref[np.isfinite(ref)]
        if not len(ref):
            bad[start : start + step] = True
            continue
        center = np.median(ref)
        scale = 1.4826 * np.median(abs(ref - center))
        segment = d[start : start + step]
        tolerance = (
            64
            * np.finfo(float).eps
            * max(float(np.nanmax(abs(x))) * fs, abs(center), np.finfo(float).tiny)
        )
        if scale > tolerance:
            bad[start : start + step] |= abs(segment - center) > multiple * scale
        else:
            bad[start : start + step] |= abs(segment - center) > tolerance
    # Flat ten-second segments are unusable, but constant slopes are retained.
    for start in range(0, n, step):
        part = x[start : start + step]
        if len(part) > 1 and np.isfinite(part).all() and np.ptp(part) == 0:
            bad[start : start + step] = True
    width = int(guard * fs) * 2 + 1
    return ndimage.maximum_filter1d(
        bad.astype(np.uint8), width, mode="constant"
    ).astype(bool)


def longest_bad_seconds(mask, fs):
    x = np.r_[False, mask, False].astype(int)
    a = np.flatnonzero(np.diff(x) == 1)
    b = np.flatnonzero(np.diff(x) == -1)
    return float(max(b - a, default=0) / fs)


def egg_spectrum(x, bad, fs, seconds=128):
    x = np.asarray(x, float)
    bad = np.asarray(bad, bool)
    nper = int(seconds * fs)
    step = nper // 2
    spectra = []
    for start in range(0, len(x) - nper + 1, step):
        part = x[start : start + nper]
        if bad[start : start + nper].any() or not np.isfinite(part).all():
            continue
        f, p = signal.periodogram(
            part, fs=fs, window="hann", detrend="constant", scaling="density"
        )
        spectra.append(p)
    if not spectra:
        return dict(status="no_clean_contiguous_spectral_segment", segments=0)
    p = np.mean(spectra, axis=0)
    ix = np.flatnonzero((f >= 1 / 60) & (f <= 9 / 60))
    peak = ix[np.argmax(p[ix])]
    total = float(np.trapezoid(p[ix], f[ix]))
    norm = (f >= 2 / 60) & (f <= 4 / 60)
    boundary = peak in [ix[0], ix[-1]]
    return dict(
        status="descriptive_peak_unvalidated"
        if len(spectra) >= 2 and not boundary
        else "peak_undetermined",
        segments=len(spectra),
        peak_cpm=float(60 * f[peak]),
        boundary=bool(boundary),
        power_1_9=total,
        normal_band_fraction=float(np.trapezoid(p[norm], f[norm]) / total)
        if total > 0
        else None,
        native_grid_cpm=60 / seconds,
    )


def hb_mean(t, x, bad, start, end):
    w = time_weights(t, start, end)
    valid = np.isfinite(x) & ~bad
    good = w * valid
    return dict(
        mean=float(np.sum(np.where(valid, x, 0) * good) / sum(good))
        if sum(good) > 0
        else None,
        coverage=float(sum(good) / (end - start)),
        longest_bad_seconds=longest_bad_seconds(
            (~valid)[w > 0], 1 / np.median(np.diff(t))
        ),
    )


def hb_means_matrix(t, x, bad, start, end):
    w = time_weights(t, start, end)
    selected = w > 0
    weights = w[selected, None, None]
    z = x[selected, :, :2]
    valid = np.isfinite(z) & ~bad[selected]
    denominator = np.sum(weights * valid, axis=0)
    means = np.divide(
        np.sum(np.where(valid, z, 0) * weights, axis=0),
        denominator,
        out=np.full_like(denominator, np.nan),
        where=denominator > 0,
    )
    return means, denominator / (end - start), valid
