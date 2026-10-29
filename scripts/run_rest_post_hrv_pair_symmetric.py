"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy import signal
import bioread
from capsaicin.ecg_rr_candidates_v2 import symmetric_rr_continuity

ROOT = Path(__file__).resolve().parents[1]
RR_LOW, RR_HIGH, JUMP = (0.3, 1.8, 0.2)
MIN_BLOCK = 2


def read_acq(path):
    with path.open("rb") as f:
        reader = bioread.reader.Reader(f)
        reader._read_headers()
        reader._read_data(None, bioread.reader.CHUNK_SIZE)
        datafile = reader.datafile
    return (
        np.vstack([np.asarray(c.data, float) for c in datafile.channels]),
        float(datafile.channels[0].samples_per_second),
        [str(c.name) for c in datafile.channels],
    )


def ecg_indices(names):
    found = [i for i, n in enumerate(names) if "ECG" in n.upper()]
    return found[:3] if len(found) >= 3 else [2, 3, 4] if len(names) == 5 else [3, 4, 5]


def peaks(ecg, fs):
    all_peaks = []
    sos = signal.butter(4, [8, 28], btype="bandpass", fs=fs, output="sos")
    for x in ecg:
        y = signal.sosfiltfilt(sos, x)
        n = max(1, round(0.12 * fs))
        energy = np.convolve(np.gradient(y) ** 2, np.ones(n) / n, mode="same")
        mad = np.median(abs(energy - np.median(energy))) * 1.4826
        p, _ = signal.find_peaks(
            energy,
            distance=round(0.2 * fs),
            prominence=max(2 * mad, np.finfo(float).eps),
        )
        all_peaks.append(p)
    tol = round(0.02 * fs)
    events = []
    for p in sorted(set((int(v) for lead in all_peaks for v in lead))):
        votes = [
            int(lead[np.argmin(abs(lead - p))])
            for lead in all_peaks
            if np.any(abs(lead - p) <= tol)
        ]
        if len(votes) >= 2:
            aligned = int(round(np.median(votes)))
            if not events or aligned - events[-1] >= round(0.2 * fs):
                events.append(aligned)
    return np.asarray(events, dtype=float) / fs


def metrics(times):
    rr = np.diff(times)
    result = symmetric_rr_continuity(rr, RR_LOW, RR_HIGH, JUMP)
    valid = result["range_valid"]
    block_ids = result["block_ids"]
    usable = valid.copy()
    counts = {int(b): int(np.sum(block_ids == b)) for b in set(block_ids) if b >= 0}
    usable &= np.array([counts.get(int(b), 0) >= MIN_BLOCK for b in block_ids])
    vals = rr[usable]
    diffs = []
    for b in sorted(set(block_ids[usable])):
        v = rr[usable & (block_ids == b)]
        if len(v) >= MIN_BLOCK:
            diffs.extend(np.diff(v).tolist())
    longest = 0.0
    for b in sorted(set(block_ids[usable])):
        v = rr[usable & (block_ids == b)]
        if len(v):
            longest = max(longest, float(np.sum(v)))
    return {
        "r_peaks": int(len(times)),
        "rr_total": int(len(rr)),
        "observed_rr_valid": int(np.sum(usable)),
        "observed_rr_valid_fraction": float(np.mean(usable)) if len(rr) else 0.0,
        "candidate_hr_bpm": float(60 / np.mean(vals)) if len(vals) else np.nan,
        "candidate_rmssd_ms": float(np.sqrt(np.mean(np.square(diffs))) * 1000)
        if diffs
        else np.nan,
        "symmetric_blocks": int(sum((n >= MIN_BLOCK for n in counts.values()))),
        "range_invalid_rr": int(np.sum(~valid)),
        "discontinuous_edges": int(np.sum(~result["edge_continuous"])),
        "longest_contiguous_s": longest,
        "semantics": "observed_rr_candidate_not_nn_or_clinical_hrv",
    }
