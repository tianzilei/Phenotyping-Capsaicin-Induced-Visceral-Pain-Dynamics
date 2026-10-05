"""RR candidate construction from multi-lead events, without NN imputation."""

from __future__ import annotations

import numpy as np


def enforce_refractory(events, fs: float, refractory_seconds: float = 0.2):
    """Keep one aligned candidate per refractory neighborhood by lead votes."""
    items = sorted(
        (int(sample), int(votes)) for sample, votes in events if int(votes) >= 2
    )
    if not items:
        return []
    distance = max(1, round(refractory_seconds * fs))
    kept = [items[0]]
    for item in items[1:]:
        if item[0] - kept[-1][0] >= distance:
            kept.append(item)
        elif item[1] > kept[-1][1]:
            kept[-1] = item
    return kept


def classify_rr_values(
    values,
    rr_low: float = 0.3,
    rr_high: float = 1.8,
    jump_fraction: float = 0.25,
    reverse: bool = False,
):
    """Classify RR values with an explicit reset after every flagged interval.

    A flagged interval ends the current local block.  The next range-valid
    interval establishes a new anchor and is marked as a re-lock boundary, so
    downstream variability summaries cannot join observations across the flag.
    """
    values = [float(value) for value in values]
    order = list(range(len(values)))
    if reverse:
        order.reverse()
    result = [None] * len(values)
    anchor = None
    block_id = 0
    seen = False
    for index in order:
        rr = values[index]
        range_ok = rr_low <= rr <= rr_high
        relock = bool(seen and anchor is None and range_ok)
        if not range_ok:
            jump_ok = False
            status = "RR_CANDIDATE_FLAGGED"
            anchor = None
        elif anchor is None:
            if relock:
                block_id += 1
            jump_ok = True
            status = "RR_CANDIDATE_LOCALLY_PLAUSIBLE"
            anchor = rr
        else:
            jump_ok = abs(rr - anchor) / max(anchor, 1e-30) <= jump_fraction
            status = (
                "RR_CANDIDATE_LOCALLY_PLAUSIBLE" if jump_ok else "RR_CANDIDATE_FLAGGED"
            )
            anchor = rr if jump_ok else None
        result[index] = {
            "range_ok": bool(range_ok),
            "local_jump_ok": bool(jump_ok),
            "status": status,
            "local_block_id": int(block_id),
            "relock_boundary": relock,
        }
        seen = True
    return result


def symmetric_rr_continuity(
    values, rr_low: float = 0.3, rr_high: float = 1.8, jump_fraction: float = 0.20
):
    """Split range-valid RR candidates at symmetric adjacent discontinuities.

    The decision belongs to the edge between two intervals, rather than to
    either endpoint.  Reversing the sequence therefore produces exactly the
    reversed block structure.  Range-invalid intervals form explicit gaps.
    """
    values = np.asarray(values, dtype=float)
    if jump_fraction <= 0:
        raise ValueError("jump_fraction must be positive")
    valid = np.isfinite(values) & (values >= rr_low) & (values <= rr_high)
    edge_ok = np.zeros(max(0, len(values) - 1), dtype=bool)
    threshold = float(np.log1p(jump_fraction))
    for index in range(1, len(values)):
        if valid[index - 1] and valid[index]:
            edge_ok[index - 1] = (
                abs(np.log(values[index] / values[index - 1])) <= threshold
            )
    block_ids = np.full(len(values), -1, dtype=int)
    block = -1
    for index in range(len(values)):
        if not valid[index]:
            continue
        if index == 0 or not valid[index - 1] or not edge_ok[index - 1]:
            block += 1
        block_ids[index] = block
    return {
        "range_valid": valid,
        "edge_continuous": edge_ok,
        "block_ids": block_ids,
        "log_threshold": threshold,
    }


def rr_candidates(
    events,
    fs: float,
    rr_low: float = 0.3,
    rr_high: float = 1.8,
    jump_fraction: float = 0.25,
    refractory_seconds: float = 0.2,
):
    """Return consecutive observed RR intervals and conservative local flags."""
    kept = enforce_refractory(events, fs, refractory_seconds)
    base = []
    for index in range(1, len(kept)):
        previous, current = kept[index - 1], kept[index]
        rr = (current[0] - previous[0]) / fs
        base.append(
            {
                "start_sample": previous[0],
                "end_sample": current[0],
                "start_seconds": previous[0] / fs,
                "end_seconds": current[0] / fs,
                "rr_seconds": rr,
                "start_lead_votes": previous[1],
                "end_lead_votes": current[1],
                "semantic_status": "observed_consecutive_rr_candidate_not_nn",
            }
        )
    flags = classify_rr_values(
        [row["rr_seconds"] for row in base], rr_low, rr_high, jump_fraction
    )
    rows = [{**row, **flag} for row, flag in zip(base, flags)]
    return rows


def rr_summary(rows):
    plausible = [
        row["rr_seconds"]
        for row in rows
        if row["status"] == "RR_CANDIDATE_LOCALLY_PLAUSIBLE"
    ]
    consecutive_pairs = [
        (rows[i - 1]["rr_seconds"], rows[i]["rr_seconds"])
        for i in range(1, len(rows))
        if (
            rows[i - 1]["status"]
            == rows[i]["status"]
            == "RR_CANDIDATE_LOCALLY_PLAUSIBLE"
            and rows[i - 1]["end_sample"] == rows[i]["start_sample"]
            and rows[i - 1].get("local_block_id") == rows[i].get("local_block_id")
            and not rows[i].get("relock_boundary", False)
        )
    ]
    rmssd = (
        float(np.sqrt(np.mean([(b - a) ** 2 for a, b in consecutive_pairs])))
        if consecutive_pairs
        else None
    )
    return {
        "rr_candidates": len(rows),
        "locally_plausible_rr": len(plausible),
        "flagged_rr": len(rows) - len(plausible),
        "candidate_hr_bpm": float(60 / np.mean(plausible)) if plausible else None,
        "candidate_rmssd_seconds": rmssd,
        "rmssd_semantics": "candidate_consecutive_plausible_rr_only_not_nn_hrv",
    }
