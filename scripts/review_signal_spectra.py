"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def integrate_independent(f, p, lo, hi):
    total = 0.0
    for i in range(len(f) - 1):
        a = max(lo, f[i])
        b = min(hi, f[i + 1])
        if a >= b:
            continue
        slope = (p[i + 1] - p[i]) / (f[i + 1] - f[i])
        total += p[i] * (b - a) + 0.5 * slope * ((b - f[i]) ** 2 - (a - f[i]) ** 2)
    return float(total)


def manual_welch(y, rate, seconds):
    n = int(rate * seconds)
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)
    x = np.arange(n, dtype=float)
    x -= x.mean()
    xx = x @ x
    parts = []
    for start in range(0, len(y) - n + 1, n // 2):
        segment = y[start : start + n].copy()
        segment -= segment.mean()
        segment -= x * (x @ segment) / xx
        psd = np.abs(np.fft.rfft(segment * window)) ** 2 / (rate * (window @ window))
        psd[1:-1] *= 2
        parts.append(psd)
    return np.mean(parts, axis=0)
