"""Threshold-state descriptions; no fitted transition-regression estimator."""

import bisect
import math
from collections import defaultdict


def describe_states(rows, thresholds, rationale):
    if not rationale or not thresholds or thresholds != sorted(set(thresholds)):
        raise ValueError("Frozen justified thresholds required")
    if any(
        isinstance(x, bool)
        or not isinstance(x, (float, int))
        or not math.isfinite(x)
        or not 0 < x < 10
        for x in thresholds
    ):
        raise ValueError("Thresholds must be strictly inside VAS 0-10")
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["subject_id"]].append(row)
    points = []
    transitions = []
    spells = []
    for sid, values in grouped.items():
        values = sorted(values, key=lambda r: r["time_min"])
        if len({r["time_min"] for r in values}) != len(values):
            raise ValueError("Duplicate subject-minute")
        observed = []
        for r in values:
            if r["status"] != "observed":
                continue
            v = r["vas"]
            if (
                not isinstance(v, (int, float))
                or not math.isfinite(v)
                or not 0 <= v <= 10
            ):
                raise ValueError("Invalid observed VAS")
            s = bisect.bisect_right(thresholds, v)
            p = dict(subject_id=sid, time_min=r["time_min"], state=s, vas=v)
            points.append(p)
            observed.append(p)
        current = None
        for i, r in enumerate(observed):
            previous = observed[i - 1] if i else None
            adjacent = (
                previous is not None and r["time_min"] - previous["time_min"] == 1
            )
            if adjacent:
                transitions.append(
                    dict(
                        subject_id=sid,
                        start_min=previous["time_min"],
                        end_min=r["time_min"],
                        from_state=previous["state"],
                        to_state=r["state"],
                    )
                )
            if current is None or not adjacent or previous["state"] != r["state"]:
                if current is not None:
                    current["right_censored"] = not adjacent
                    current["right_boundary"] = (
                        "observation_gap" if not adjacent else "observed_transition"
                    )
                    spells.append(current)
                current = dict(
                    subject_id=sid,
                    state=r["state"],
                    start_min=r["time_min"],
                    end_min=r["time_min"],
                    n_observed=1,
                    observed_span_min=0,
                    left_censored=not adjacent,
                    left_boundary="observation_start_or_gap"
                    if not adjacent
                    else "observed_transition",
                )
            else:
                current["end_min"] = r["time_min"]
                current["n_observed"] += 1
                current["observed_span_min"] = current["end_min"] - current["start_min"]
        if current is not None:
            current["right_censored"] = True
            current["right_boundary"] = "observation_end"
            spells.append(current)
    return dict(points=points, transitions=transitions, spells=spells)
