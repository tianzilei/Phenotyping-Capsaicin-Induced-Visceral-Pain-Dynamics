"""Multi-lead candidate stability diagnostics without reference-accuracy claims."""

from __future__ import annotations
import numpy as np
from .electrophysiology_qc_v2 import event_clusters
from .ecg_rr_candidates_v2 import symmetric_rr_continuity


def consensus_times(
    lead_peaks, fs: float, tolerance_seconds: float = 0.03, minimum_votes: int = 2
):
    return np.asarray(
        [
            time
            for time, votes in event_clusters(lead_peaks, fs, tolerance_seconds)
            if votes >= minimum_votes
        ],
        dtype=int,
    )


def tolerant_event_jaccard(
    reference, candidate, fs: float, tolerance_seconds: float = 0.03
):
    """One-to-one time-tolerant event Jaccard."""
    reference = np.asarray(reference, dtype=int)
    candidate = np.asarray(candidate, dtype=int)
    tolerance = max(0, round(tolerance_seconds * fs))
    i = j = matches = 0
    while i < len(reference) and j < len(candidate):
        delta = candidate[j] - reference[i]
        if abs(delta) <= tolerance:
            matches += 1
            i += 1
            j += 1
        elif delta < 0:
            j += 1
        else:
            i += 1
    union = len(reference) + len(candidate) - matches
    return float(matches / union) if union else 1.0, matches


def candidate_rmssd_ms(events, fs: float, jump_fraction: float = 0.20):
    values = np.diff(np.asarray(events, dtype=float)) / fs
    continuity = symmetric_rr_continuity(values, jump_fraction=jump_fraction)
    grouped = {}
    for value, valid, block in zip(
        values, continuity["range_valid"], continuity["block_ids"]
    ):
        if valid:
            grouped.setdefault(int(block), []).append(float(value))
    diffs = [b - a for vals in grouped.values() for a, b in zip(vals[:-1], vals[1:])]
    return float(np.sqrt(np.mean(np.square(diffs))) * 1000) if diffs else None
