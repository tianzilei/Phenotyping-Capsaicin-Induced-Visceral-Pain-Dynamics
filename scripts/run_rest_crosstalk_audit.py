"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import numpy as np
from scipy import signal
from run_rest_waveform_qc import SPEC
from capsaicin.crosstalk_calibration import subtract_frozen_template

ROOT = Path(__file__).resolve().parents[1]
FS = 100.0
INJECT_CPM = 3.0
INJECT_AMPLITUDE = 50.0


def qrs_rms(x, fs, peaks):
    sos = signal.butter(4, [8.0, 25.0], btype="bandpass", fs=fs, output="sos")
    z = signal.sosfiltfilt(sos, x)
    vals = []
    for p in peaks:
        a, b = (int(p - 0.1 * fs), int(p + 0.15 * fs))
        if a >= 0 and b <= len(z):
            vals.append(float(np.sqrt(np.mean(z[a:b] ** 2))))
    return np.asarray(vals)


def fit_sine(x, fs, cpm=INJECT_CPM):
    t = np.arange(len(x), dtype=float) / fs
    w = 2 * np.pi * cpm / 60.0
    A = np.column_stack([np.sin(w * t), np.cos(w * t)])
    beta, *_ = np.linalg.lstsq(A, x, rcond=None)
    fit = A @ beta
    amp = float(np.hypot(beta[0], beta[1]))
    phase = float(np.arctan2(beta[1], beta[0]))
    return (amp, phase, fit)


def injection_audit(raw, peaks, template, fs):
    t = np.arange(raw.shape[1], dtype=float) / fs
    w = 2 * np.pi * INJECT_CPM / 60.0
    injected = np.tile(INJECT_AMPLITUDE * np.sin(w * t), (raw.shape[0], 1))
    base, _ = subtract_frozen_template(raw, peaks, template, fs, SPEC)
    pert, _ = subtract_frozen_template(raw + injected, peaks, template, fs, SPEC)
    rows = []
    for ch in range(raw.shape[0]):
        recovered = pert[ch] - base[ch]
        amp, phase, fit = fit_sine(recovered, fs)
        target_phase = 0.0
        phase_err = float(
            np.arctan2(np.sin(phase - target_phase), np.cos(phase - target_phase))
        )
        rmse = float(
            np.sqrt(np.mean((recovered - injected[ch]) ** 2)) / INJECT_AMPLITUDE
        )
        rows.append((amp / INJECT_AMPLITUDE, abs(phase_err), rmse))
    return rows


def projection_audit(raw, peaks, template, fs):
    vals = []
    left, right = (
        round(SPEC.window_seconds[0] * fs),
        round(SPEC.window_seconds[1] * fs),
    )
    for p in np.asarray(peaks, dtype=int):
        a, b = (p + left, p + right)
        if a < 0 or b > raw.shape[1]:
            continue
        for ch in range(raw.shape[0]):
            y = raw[ch, a:b]
            t = template[ch]
            yc, tc = (y - y.mean(), t - t.mean())
            den = float(np.dot(tc, tc))
            if den <= 1e-15 or np.std(yc) <= 0:
                continue
            vals.append(
                (
                    float(np.corrcoef(yc, tc)[0, 1]),
                    float(np.dot(yc, tc) / den),
                    float(np.sqrt(np.mean(yc**2))),
                    float(np.sqrt(np.mean(tc**2))),
                )
            )
    return np.asarray(vals, dtype=float)
