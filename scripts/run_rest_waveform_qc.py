"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy import signal
import bioread

ROOT = Path(__file__).resolve().parents[1]


def read_acq(p: Path):
    with p.open("rb") as f:
        r = bioread.reader.Reader(f)
        r._read_headers()
        r._read_data(None, bioread.reader.CHUNK_SIZE)
        d = r.datafile
    arr = np.vstack([np.asarray(c.data, dtype=float) for c in d.channels])
    fs = float(d.channels[0].samples_per_second)
    names = [str(c.name) for c in d.channels]
    return (arr, fs, names)


def channel_indices(names):
    ecg = [i for i, n in enumerate(names) if "ECG" in n.upper()]
    egg = [i for i, n in enumerate(names) if "EGG" in n.upper()]
    if len(ecg) < 3 or len(egg) < 2:
        if len(names) in (5,):
            ecg, egg = ([2, 3, 4], [0, 1])
        elif len(names) in (6, 7):
            ecg, egg = ([3, 4, 5], [1, 2])
    return (ecg[:3], egg[:2])


def quality(x, fs):
    finite = np.isfinite(x)
    xf = x[finite]
    if xf.size == 0:
        return dict(
            finite_fraction=0,
            saturation_fraction=1,
            flatline_fraction=1,
            robust_range=np.nan,
        )
    med = float(np.median(xf))
    dev = np.abs(xf - med)
    scale = float(np.percentile(dev, 99.9))
    sat = np.mean(dev >= max(scale, 1e-12))
    d = np.diff(x, prepend=x[:1])
    flat = np.abs(d) <= max(np.nanpercentile(np.abs(d[finite]), 1), 1e-12)
    maxrun = run_max(flat)
    return dict(
        finite_fraction=float(np.mean(finite)),
        saturation_fraction=float(sat),
        flatline_fraction=float(maxrun / max(len(x), 1)),
        robust_range=float(np.percentile(xf, 99) - np.percentile(xf, 1)),
    )


def run_max(mask):
    best = cur = 0
    for v in np.asarray(mask, dtype=bool):
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def downsample(x, fs, target=100):
    if abs(fs - target) < 1e-06:
        return (x, fs)
    g = np.gcd(int(round(fs)), target)
    y = signal.resample_poly(x, target // g, int(round(fs)) // g, axis=-1)
    return (y, float(target))


def r_peaks(ecg, fs):
    cfg = {
        "bandpass_hz": [8.0, 28.0],
        "filter_order": 4,
        "energy_window_seconds": 0.12,
        "refractory_seconds": 0.2,
        "consensus_tolerance_seconds": 0.02,
        "snr_min_db": 6.0,
    }
    leads = []
    for x in ecg:
        sos = signal.butter(
            cfg["filter_order"],
            cfg["bandpass_hz"],
            btype="bandpass",
            fs=fs,
            output="sos",
        )
        y = signal.sosfiltfilt(sos, x)
        n = max(1, round(cfg["energy_window_seconds"] * fs))
        e = np.convolve(np.gradient(y) ** 2, np.ones(n) / n, mode="same")
        mad = np.median(np.abs(e - np.median(e))) * 1.4826
        p, _ = signal.find_peaks(
            e, distance=round(0.2 * fs), prominence=max(2 * mad, np.finfo(float).eps)
        )
        leads.append(p)
    tol = round(0.02 * fs)
    allp = sorted(set((int(v) for a in leads for v in a)))
    events = []
    for p in allp:
        near = [
            int(a[np.argmin(np.abs(a - p))])
            for a in leads
            if np.any(np.abs(a - p) <= tol)
        ]
        if len(near) >= 2:
            q = int(round(np.median(near)))
            if not events or q - events[-1] >= round(0.2 * fs):
                events.append(q)
    return (np.asarray(events, dtype=int), [len(a) for a in leads])


def egg_metrics(egg, fs):
    x, fs2 = downsample(egg, fs, 100)
    fs = fs2
    finite = np.all(np.isfinite(x), axis=0)
    out = []
    for ch in x:
        y = ch.copy()
        y[~np.isfinite(y)] = (
            np.nanmedian(y[np.isfinite(y)]) if np.any(np.isfinite(y)) else 0
        )
        sos = signal.butter(4, [0.015, 0.15], btype="bandpass", fs=fs, output="sos")
        z = signal.sosfiltfilt(sos, y)
        f, p = signal.welch(
            z, fs=fs, nperseg=min(len(z), int(240 * fs)), detrend="linear"
        )
        b = (f >= 0.015) & (f <= 0.15)
        i = np.flatnonzero(b)
        k = i[np.argmax(p[i])] if len(i) else 0
        slow = (f >= 0.033) & (f <= 0.067)
        out.append(
            {
                "dominant_cpm": float(f[k] * 60) if len(i) else np.nan,
                "slow_power_ratio": float(
                    np.trapezoid(p[slow], f[slow])
                    / max(np.trapezoid(p[b], f[b]), 1e-20)
                )
                if len(i)
                else np.nan,
                "valid_fraction": float(np.mean(np.isfinite(ch))),
            }
        )
    cf, cp = signal.coherence(x[0], x[1], fs=fs, nperseg=min(len(x[0]), int(120 * fs)))
    cband = (cf >= 0.033) & (cf <= 0.067)
    coherence = float(np.nanmax(cp[cband])) if np.any(cband) else np.nan
    return (out, coherence, x, fs)


def band_power(x, fs, lo=0.8, hi=1.5):
    f, p = signal.welch(x, fs=fs, nperseg=min(len(x), int(120 * fs)), detrend="linear")
    return float(np.trapezoid(p[(f >= lo) & (f <= hi)], f[(f >= lo) & (f <= hi)]))
