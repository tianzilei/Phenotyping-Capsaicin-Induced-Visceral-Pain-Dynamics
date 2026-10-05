"""Conservative event-clock diagnostics; periodic agreement is not event identity."""

import math
import statistics


def complete_vas(row):
    values = []
    for minute in range(1, 21):
        try:
            value = float(row.get(f"VAS_{minute}min", ""))
        except (ValueError, TypeError):
            return False
        if not math.isfinite(value) or not 0 <= value <= 10:
            return False
        values.append(value)
    return len(values) == 20


def cluster_edges(times, tolerance):
    """Keep all native edges elsewhere; cluster short TTL bursts by first edge."""
    if tolerance < 0 or any(not math.isfinite(x) for x in times):
        raise ValueError("Finite edge times and nonnegative tolerance required")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Strictly increasing edge times required")
    groups = []
    for t in times:
        if not groups or t - groups[-1][0] > tolerance:
            groups.append([t])
        else:
            groups[-1].append(t)
    return groups


def match_offset(a, b, offset, tolerance):
    """Maximum cardinality monotone one-to-one matches at a fixed offset."""
    pairs = []
    i = j = 0
    while i < len(a) and j < len(b):
        delta = a[i] + offset - b[j]
        if abs(delta) <= tolerance + 1e-9:
            pairs.append((i, j))
            i += 1
            j += 1
        elif delta < 0:
            i += 1
        else:
            j += 1
    return pairs


def audit_offsets(a, b, cfg):
    for values in (a, b):
        if any(not math.isfinite(x) for x in values) or any(
            y <= x for x, y in zip(values, values[1:])
        ):
            raise ValueError("Finite strictly increasing event clocks required")
    if not a or not b:
        return {"status": "missing_events", "candidates": [], "pairs": []}
    tol = cfg["match_tolerance_seconds"]
    solutions = {}
    # Include interval endpoints and their midpoints: all possible matching
    # cardinalities for a constant offset are represented, not just nearest offsets.
    boundaries = sorted({y - x + s * tol for x in a for y in b for s in (-1, 1)})
    seeds = boundaries + [(x + y) / 2 for x, y in zip(boundaries, boundaries[1:])]
    for seed in seeds:
        pairs = match_offset(a, b, seed, tol)
        if not pairs:
            continue
        offset = statistics.median(b[j] - a[i] for i, j in pairs)
        # Keep the original solution if median refit loses matches.
        refit = match_offset(a, b, offset, tol)
        if len(refit) >= len(pairs):
            pairs = refit
        else:
            offset = seed
        errors = [b[j] - a[i] - offset for i, j in pairs]
        key = tuple(pairs)
        candidate = dict(
            offset_s=offset,
            matches=len(pairs),
            max_residual_s=max(map(abs, errors)),
            span_s=a[pairs[-1][0]] - a[pairs[0][0]],
            pairs=pairs,
        )
        if (
            key not in solutions
            or candidate["max_residual_s"] < solutions[key]["max_residual_s"]
        ):
            solutions[key] = candidate
    ranked = sorted(
        solutions.values(),
        key=lambda x: (-x["matches"], x["max_residual_s"], abs(x["offset_s"])),
    )
    best = ranked[0]
    alternatives = [
        x
        for x in ranked[1:]
        if x["matches"] >= best["matches"] - cfg["alternative_match_count_margin"]
        and abs(x["offset_s"] - best["offset_s"]) > cfg["distinct_offset_seconds"]
    ]
    status = "unique_clock_candidate_needs_event_anchor"
    if (
        best["matches"] < cfg["minimum_matches"]
        or best["span_s"] < cfg["minimum_span_seconds"]
    ):
        status = "insufficient_event_support"
    elif alternatives:
        status = "ambiguous_periodic_offset"
    return dict(
        status=status,
        candidates=ranked,
        pairs=best["pairs"],
        alternative_offsets=len(alternatives),
        **{k: v for k, v in best.items() if k != "pairs"},
    )
