"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
TOL = 0.03
RRLO = 0.3
RRHI = 1.8
JUMP = 0.25


def ecg_indices(names):
    x = [i for i, n in enumerate(names) if "ECG" in n.upper()]
    return x[:3] if len(x) >= 3 else [2, 3, 4] if len(names) == 5 else [3, 4, 5]


def lead_peaks(x, fs):
    sos = signal.butter(4, [8, 28], btype="bandpass", fs=fs, output="sos")
    y = signal.sosfiltfilt(sos, x)
    n = max(1, round(0.12 * fs))
    e = np.convolve(np.gradient(y) ** 2, np.ones(n) / n, mode="same")
    mad = np.median(abs(e - np.median(e))) * 1.4826
    p, _ = signal.find_peaks(
        e, distance=round(0.2 * fs), prominence=max(2 * mad, np.finfo(float).eps)
    )
    return (p.astype(int), y)


def consensus(ps, fs):
    allp = sorted(set((int(v) for p in ps for v in p)))
    used = []
    events = []
    tol = round(TOL * fs)
    for p in allp:
        near = [int(a[np.argmin(abs(a - p))]) for a in ps if np.any(abs(a - p) <= tol)]
        if len(near) >= 2:
            z = int(round(np.median(near)))
            if not events or z - events[-1] >= round(0.2 * fs):
                events.append(z)
    return np.asarray(events, dtype=int)


def morph_score(raw, events, fs):
    sos = signal.butter(4, [8, 28], btype="bandpass", fs=fs, output="sos")
    ys = np.asarray([signal.sosfiltfilt(sos, x) for x in raw])
    pieces = []
    aoff = round(-0.05 * fs)
    boff = round(0.05 * fs)
    for p in events:
        a, b = (p + aoff, p + boff)
        if a >= 0 and b <= ys.shape[1]:
            pieces.append(ys[:, a:b])
    if len(pieces) < 3:
        return 0.0
    z = np.asarray(pieces)
    templ = np.median(z, axis=0)
    vals = []
    for q in z:
        for ch in range(z.shape[1]):
            if np.std(q[ch]) > 0 and np.std(templ[ch]) > 0:
                vals.append(max(0, float(np.corrcoef(q[ch], templ[ch])[0, 1])))
    return float(np.median(vals)) if vals else 0.0


def rr_score(events, fs):
    rr = np.diff(events) / fs
    if len(rr) == 0:
        return 0.0
    ok = (rr >= RRLO) & (rr <= RRHI)
    pair = (
        ok[1:]
        & ok[:-1]
        & (np.abs(rr[1:] - rr[:-1]) / np.maximum(rr[:-1], 1e-12) <= JUMP)
        if len(rr) > 1
        else np.array([], bool)
    )
    return float(np.mean(ok)) * 0.5 + (float(np.mean(pair)) if len(pair) else 0.0) * 0.5


def neg_score(raw, fs, events):
    rng = np.random.default_rng(20260929)
    shuffled = np.asarray([x[rng.permutation(len(x))] for x in raw])
    ps = [lead_peaks(x, fs)[0] for x in shuffled]
    n = len(consensus(ps, fs))
    d = max(len(events), 1)
    return float(max(0, 1 - n / d))
