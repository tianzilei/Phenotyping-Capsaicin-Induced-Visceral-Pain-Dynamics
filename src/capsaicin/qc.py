"""Descriptive QC only; no inferred post-termination pain and no gap bridging."""

from collections import Counter, defaultdict
import math

STATUSES = ("observed", "missing", "termination_E", "termination_T", "post_termination")


def time_counts(rows):
    counts = defaultdict(Counter)
    for row in rows:
        counts[row["time_min"]][row["status"]] += 1
    return [
        dict(
            time_min=t,
            n_scheduled=sum(c.values()),
            **{"n_" + status: c[status] for status in STATUSES},
        )
        for t, c in sorted(counts.items())
    ]


def subject_descriptives(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["subject_id"]].append(row)
    result = []
    for sid, series in sorted(groups.items()):
        observed = sorted(
            (r for r in series if r["status"] == "observed"),
            key=lambda r: r["time_min"],
        )
        values = [r["vas"] for r in observed]
        differences = [
            (b["vas"] - a["vas"]) ** 2
            for a, b in zip(observed, observed[1:])
            if math.isclose(b["time_min"] - a["time_min"], 1, abs_tol=1e-9)
        ]
        markers = [r for r in series if r["status"].startswith("termination_")]
        average = sum(values) / len(values) if values else None
        sd = (
            math.sqrt(sum((v - average) ** 2 for v in values) / (len(values) - 1))
            if len(values) > 1
            else None
        )
        result.append(
            dict(
                subject_id=sid,
                n_observed=len(values),
                n_adjacent_pairs=len(differences),
                mean_observed_vas=average,
                raw_sd=sd,
                raw_mssd=sum(differences) / len(differences) if differences else None,
                last_observed_min=observed[-1]["time_min"] if observed else None,
                termination_code=markers[0]["termination_code"] if markers else "",
                first_marker_min=min(r["time_min"] for r in markers)
                if markers
                else None,
            )
        )
    return result
