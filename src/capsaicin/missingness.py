"""Non-imputing missingness classification for scheduled VAS minutes."""

from collections import defaultdict
import statistics


def classify_subject(rows, minutes=range(1, 21)):
    minutes = list(minutes)
    if minutes != sorted(set(minutes)) or any(
        b - a != 1 for a, b in zip(minutes, minutes[1:])
    ):
        raise ValueError("Expected consecutive scheduled minutes")
    by = {r["time_min"]: r for r in rows}
    if len(by) != len(rows):
        raise ValueError("Duplicate subject minute")
    marker_rows = [r for r in rows if r["status"] in ("termination_E", "termination_T")]
    first = min(marker_rows, key=lambda r: r["time_min"]) if marker_rows else None
    marker = first["termination_code"] if first else "none"
    first_min = first["time_min"] if first else None
    statuses = []
    for t in minutes:
        r = by.get(t)
        if r is None:
            raise ValueError("Missing scheduled minute")
        if r["status"] == "observed":
            cat = "observed"
        elif r["status"] in ("termination_E", "termination_T"):
            cat = r["status"]
        elif first and t > first_min:
            cat = "post_termination_missing"
        else:
            cat = "pre_marker_missing"
        statuses.append(cat)
    longest = 0
    run = 0
    for c in statuses:
        run = run + 1 if c == "pre_marker_missing" else 0
        longest = max(longest, run)
    observed = [t for t, c in zip(minutes, statuses) if c == "observed"]
    return dict(
        eventual_marker=marker,
        first_marker_min=first_min,
        n_observed=len(observed),
        n_pre_marker_missing=statuses.count("pre_marker_missing"),
        n_post_termination_missing=statuses.count("post_termination_missing"),
        longest_pre_marker_gap=longest,
        last_observed_min=max(observed) if observed else None,
        pattern="|".join(statuses),
        **{f"minute_{t}": c for t, c in zip(minutes, statuses)},
    )


def classify_all(rows, minutes=range(1, 21)):
    groups = defaultdict(list)
    for r in rows:
        groups[r["subject_id"]].append(r)
    return [
        dict(subject_id=sid, **classify_subject(rs, minutes))
        for sid, rs in sorted(groups.items())
    ]


def adjacent_composition(rows, minutes=range(1, 21)):
    """Exact decomposition of observed mean differences; no causal attribution."""
    obs = defaultdict(dict)
    for r in rows:
        if r["status"] == "observed":
            obs[r["time_min"]][r["subject_id"]] = r["vas"]
    result = []
    for a, b in zip(minutes, list(minutes)[1:]):
        if b - a != 1:
            raise ValueError("No bridging missing minutes")
        x, y = obs[a], obs[b]
        both = set(x) & set(y)
        total = (
            statistics.mean(y.values()) - statistics.mean(x.values())
            if x and y
            else None
        )
        within = statistics.mean(y[i] - x[i] for i in sorted(both)) if both else None
        left = (
            statistics.mean(x[i] for i in sorted(both)) - statistics.mean(x.values())
            if both
            else None
        )
        right = (
            statistics.mean(y.values()) - statistics.mean(y[i] for i in sorted(both))
            if both
            else None
        )
        result.append(
            dict(
                start_min=a,
                end_min=b,
                n_start=len(x),
                n_end=len(y),
                n_both=len(both),
                n_leaving=len(set(x) - set(y)),
                n_entering=len(set(y) - set(x)),
                observed_mean_change=total,
                paired_observed_change=within,
                start_composition=left,
                end_composition=right,
                composition_total=left + right if both else None,
                defined=bool(both),
            )
        )
    return result
