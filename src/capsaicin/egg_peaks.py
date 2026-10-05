"""Describe competing spectral maxima without certifying a gastric rhythm."""

import numpy as np
from scipy import signal
from capsaicin.signal_spectra import band_area, welch_description


def peak_descriptors(f, p, broad=(0.0083, 0.15)):
    f = np.asarray(f)
    p = np.asarray(p)
    if (
        f.ndim != 1
        or p.shape != f.shape
        or not np.isfinite(p).all()
        or np.any(p < 0)
        or not np.all(np.diff(f) > 0)
    ):
        raise ValueError("Finite nonnegative PSD on increasing frequency grid required")
    indices = np.flatnonzero((f >= broad[0]) & (f <= broad[1]))
    if len(indices) < 3:
        raise ValueError("Insufficient frequency support")
    if not np.any(p[indices] > 0):
        return dict(status="zero_band_power"), []
    winner = int(indices[np.argmax(p[indices])])
    # Local maxima must have neighbors inside the band; the band edges never count.
    local = [int(i) for i in indices[1:-1] if p[i] > p[i - 1] and p[i] > p[i + 1]]
    peaks = [dict(frequency_hz=float(f[i]), psd=float(p[i])) for i in local]
    best = max(local, key=lambda i: p[i]) if local else None
    result = dict(
        status="described_not_validated",
        maximum_hz=float(f[winner]),
        boundary_maximum=bool(winner in (indices[0], indices[-1])),
        local_peak_count=len(local),
        strongest_local_hz=float(f[best]) if best is not None else None,
        strongest_local_to_max=float(p[best] / p[winner]) if best is not None else None,
    )
    total = band_area(f, p, *broad)
    for key, lo, hi in [
        ("low", 0.0083, 0.033),
        ("middle", 0.033, 0.067),
        ("high", 0.067, 0.15),
    ]:
        result[key + "_fraction"] = (
            band_area(f, p, lo, hi) / total if total > 0 else None
        )
    return result, peaks


def variant_spectrum(y, rate, variant):
    x = np.asarray(y, dtype=float)
    degree = variant["window_polynomial_degree"]
    if degree:
        t = np.linspace(-1, 1, len(x))
        design = np.vander(t, degree + 1, increasing=True)
        x = x - design @ np.linalg.lstsq(design, x, rcond=None)[0]
    f, p, n = welch_description(x, rate, variant["segment_seconds"])
    result, peaks = peak_descriptors(f, p)
    result.update(
        variant=variant["name"], segments=n, frequency_step_hz=float(f[1] - f[0])
    )
    return result, peaks, (f, p)
