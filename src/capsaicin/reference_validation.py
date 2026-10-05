"""Reference admission and continuous NN calculations; no reference is inferred."""

from __future__ import annotations

import math
import statistics


def reference_contract(metadata, expected_sha256):
    required = (
        "source_sha256",
        "reviewer_id",
        "independence_attestation",
        "adjudication_id",
        "annotation_version",
    )
    missing = [key for key in required if not metadata.get(key)]
    if metadata.get("source_sha256") != expected_sha256:
        missing.append("source_hash_mismatch")
    if metadata.get("independence_attestation") != "independent_human_attested":
        missing.append("independence_not_attested")
    return {
        "admissible_contract": not missing,
        "reasons": sorted(set(missing)),
        "meaning": "documented contract only; not proof of reference correctness",
    }


def match_events(reference, candidates, tolerance):
    """Ordered one-to-one maximum matching, then minimum total timing error."""
    for values in (reference, candidates):
        if any(not math.isfinite(v) for v in values):
            raise ValueError("Nonfinite event time")
        if any(b <= a for a, b in zip(values, values[1:])):
            raise ValueError("Strictly increasing event times required")
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Nonnegative finite tolerance required")
    # Full traceback; intended for finite evaluation windows, not entire files.
    n, m = len(reference), len(candidates)
    previous = [(0, 0.0)] * (m + 1)
    trace = [bytearray(m + 1) for _ in range(n + 1)]
    better = lambda a, b: (a[0], -a[1]) > (b[0], -b[1])
    for i in range(1, n + 1):
        current = [(0, 0.0)] * (m + 1)
        for j in range(1, m + 1):
            best, move = previous[j], 1
            if better(current[j - 1], best):
                best, move = current[j - 1], 2
            error = abs(reference[i - 1] - candidates[j - 1])
            if error <= tolerance:
                matched = (previous[j - 1][0] + 1, previous[j - 1][1] + error)
                if better(matched, best):
                    best, move = matched, 3
            current[j], trace[i][j] = best, move
        previous = current
    pairs, i, j = [], n, m
    while i and j:
        move = trace[i][j]
        if move == 3:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif move == 2:
            j -= 1
        else:
            i -= 1
    pairs.reverse()
    errors = [candidates[j] - reference[i] for i, j in pairs]
    tp = len(pairs)
    return {
        "pairs": pairs,
        "TP": tp,
        "FN": n - tp,
        "FP": m - tp,
        "sensitivity": tp / n if n else None,
        "positive_predictive_value": tp / m if m else None,
        "timing_error_s": errors,
        "mean_absolute_timing_error_s": statistics.mean(map(abs, errors))
        if errors
        else None,
    }


def reference_nn_hrv(beats, start_s, end_s, unreadable=()):
    """Use adjacent annotated normal beats; never join across a rejected interval."""
    if not math.isfinite(start_s) or not math.isfinite(end_s) or end_s <= start_s:
        raise ValueError("Invalid window")
    if any(b["beat_type"] not in {"normal", "abnormal", "uncertain"} for b in beats):
        raise ValueError("Unknown beat class")
    times = [float(b["time_s"]) for b in beats]
    if any(not math.isfinite(t) for t in times) or any(
        b <= a for a, b in zip(times, times[1:])
    ):
        raise ValueError("Invalid beat order")
    for a, b in unreadable:
        if not math.isfinite(a) or not math.isfinite(b) or b <= a:
            raise ValueError("Invalid unreadable interval")
    intervals = []
    for i in range(len(beats) - 1):
        a, b = times[i : i + 2]
        # Both peaks must be inside the predefined half-open window.
        inside = start_s <= a < b < end_s
        normal = beats[i]["beat_type"] == beats[i + 1]["beat_type"] == "normal"
        blocked = any(a < hi and b > lo for lo, hi in unreadable)
        valid = inside and normal and not blocked
        intervals.append(
            {
                "original_interval_index": i,
                "start_s": a,
                "end_s": b,
                "nn_ms": 1000 * (b - a) if valid else None,
                "valid": valid,
            }
        )
    values = [r["nn_ms"] for r in intervals if r["valid"]]
    changes = [
        (b["nn_ms"] - a["nn_ms"]) ** 2
        for a, b in zip(intervals, intervals[1:])
        if a["valid"] and b["valid"]
    ]
    eligible = sum(start_s <= a < b < end_s for a, b in zip(times, times[1:]))
    return {
        "nn_count": len(values),
        "adjacent_nn_change_count": len(changes),
        "eligible_interval_count": eligible,
        "nn_fraction": len(values) / eligible if eligible else None,
        "mean_nn_ms": statistics.mean(values) if values else None,
        "sdnn_ms": statistics.stdev(values) if len(values) >= 2 else None,
        "rmssd_ms": math.sqrt(statistics.mean(changes)) if changes else None,
        "window_seconds": end_s - start_s,
        "intervals": intervals,
        "role": "reference-derived descriptive metrics; eligibility and accuracy must be assessed separately",
    }


def named_clock_fit(anchors):
    """Fit drift only to known corresponding events; hold out at least one anchor."""
    names = [r["event_identity"] for r in anchors]
    if not anchors or len(set(names)) != len(names) or any(not n for n in names):
        raise ValueError("Unique named event identities required")
    train = [r for r in anchors if r["role"] == "fit"]
    holdout = [r for r in anchors if r["role"] == "holdout"]
    if len(train) < 2 or not holdout:
        return {"status": "insufficient_named_anchor_support"}
    vals = [(float(r["acq_s"]), float(r["hb_s"])) for r in anchors]
    if any(not math.isfinite(v) for pair in vals for v in pair):
        raise ValueError("Nonfinite clock anchor")
    xs = [float(r["acq_s"]) for r in train]
    ys = [float(r["hb_s"]) for r in train]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        raise ValueError("No clock span")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    if slope <= 0:
        raise ValueError("Nonpositive clock rate")
    offset = my - slope * mx
    errors = [float(r["hb_s"]) - offset - slope * float(r["acq_s"]) for r in holdout]
    return {
        "status": "named_clock_fit_requires_target_tolerance",
        "offset_s": offset,
        "drift_ppm": (slope - 1) * 1e6,
        "holdout_error_s": errors,
        "max_abs_holdout_error_s": max(map(abs, errors)),
        "fit_span_s": max(xs) - min(xs),
        "holdout_count": len(holdout),
    }


def clinical_label_contract(rows):
    required = (
        "subject_id",
        "clinical_target",
        "reference_label",
        "assessor_id",
        "assessment_time",
        "reference_source",
        "independent_of_trajectory",
    )
    errors, ids = [], set()
    for i, row in enumerate(rows):
        errors.extend(f"row_{i}:{key}_missing" for key in required if not row.get(key))
        if row.get("subject_id") in ids:
            errors.append(f"row_{i}:duplicate_subject")
        ids.add(row.get("subject_id"))
        if row.get("independent_of_trajectory") != "yes":
            errors.append(f"row_{i}:reference_not_independent")
    return {
        "status": "contract_documented_needs_target_review"
        if rows and not errors
        else "pending_independent_clinical_reference",
        "errors": errors,
        "subjects": len(rows),
    }
