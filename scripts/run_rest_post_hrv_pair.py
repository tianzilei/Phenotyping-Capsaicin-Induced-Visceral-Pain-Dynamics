"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy import signal
import bioread

ROOT = Path(__file__).resolve().parents[1]


def read(p):
    with p.open("rb") as f:
        r = bioread.reader.Reader(f)
        r._read_headers()
        r._read_data(None, bioread.reader.CHUNK_SIZE)
        d = r.datafile
    return (
        np.vstack([np.asarray(c.data, float) for c in d.channels]),
        float(d.channels[0].samples_per_second),
        [str(c.name) for c in d.channels],
    )


def inds(names):
    ecg = [i for i, n in enumerate(names) if "ECG" in n.upper()]
    if len(ecg) < 3:
        ecg = [2, 3, 4] if len(names) == 5 else [3, 4, 5]
    return ecg[:3]


def peaks(ecg, fs):
    allp = []
    for x in ecg:
        sos = signal.butter(4, [8, 28], btype="bandpass", fs=fs, output="sos")
        y = signal.sosfiltfilt(sos, x)
        n = round(0.12 * fs)
        e = np.convolve(np.gradient(y) ** 2, np.ones(n) / n, mode="same")
        mad = np.median(abs(e - np.median(e))) * 1.4826
        p, _ = signal.find_peaks(
            e, distance=round(0.2 * fs), prominence=max(2 * mad, np.finfo(float).eps)
        )
        allp.append(p)
    tol = round(0.02 * fs)
    ev = []
    for p in sorted(set((int(v) for a in allp for v in a))):
        q = [int(a[np.argmin(abs(a - p))]) for a in allp if np.any(abs(a - p) <= tol)]
        if len(q) >= 2:
            z = int(round(np.median(q)))
            if not ev or z - ev[-1] >= round(0.2 * fs):
                ev.append(z)
    return np.asarray(ev, float) / fs


def metrics(times, duration):
    if len(times) < 3:
        return {
            "r_peaks": len(times),
            "rr_total": max(len(times) - 1, 0),
            "nn_valid": 0,
            "nn_valid_fraction": 0.0,
            "mean_hr_bpm": np.nan,
            "rmssd_ms": np.nan,
            "longest_contiguous_s": 0.0,
            "sampen_status": "ECG_SAMPEN_INESTIMABLE",
        }
    rr = np.diff(times)
    good = (rr >= 0.3) & (rr <= 2.0)
    for i in range(1, len(rr)):
        good[i] &= abs(rr[i] - rr[i - 1]) / max(rr[i - 1], 1e-09) <= 0.2
    for i in range(len(rr)):
        lo = max(0, i - 5)
        hi = min(len(rr), i + 6)
        med = np.median(rr[lo:hi])
        mad = np.median(abs(rr[lo:hi] - med)) * 1.4826
        if mad > 0:
            good[i] &= abs(rr[i] - med) <= 3 * mad
    valid = rr[good]
    frac = float(np.mean(good)) if len(good) else 0.0
    adj = good[:-1] & good[1:]
    rmssd = (
        float(np.sqrt(np.mean(np.diff(rr[:-1][adj], axis=0) ** 2)) * 1000)
        if np.any(adj)
        else np.nan
    )
    if np.any(adj):
        rmssd = float(np.sqrt(np.mean((rr[1:][adj] - rr[:-1][adj]) ** 2)) * 1000)
    meanhr = float(60 / np.mean(valid)) if len(valid) else np.nan
    starts = np.where(good)[0]
    longest = 0
    if len(starts):
        run = 1
        for a, b in zip(starts[:-1], starts[1:]):
            run = run + 1 if b == a + 1 else 1
            longest = max(longest, run)
        longest = max(longest, run) * float(np.median(rr[good]))
    return {
        "r_peaks": len(times),
        "rr_total": len(rr),
        "nn_valid": int(np.sum(good)),
        "nn_valid_fraction": frac,
        "mean_hr_bpm": meanhr,
        "rmssd_ms": rmssd,
        "longest_contiguous_s": float(longest),
        "sampen_status": "estimable_candidate"
        if longest >= 120
        else "ECG_SAMPEN_INESTIMABLE",
    }
