"""Observed raw variability; gaps and termination are never imputed."""

import math
import statistics


def window_metrics(rows, start, end):
    selected = [r for r in rows if start <= r["time_min"] <= end]
    times = [r["time_min"] for r in selected]
    if len(times) != len(set(times)):
        raise ValueError("Duplicate subject-minute")
    values = {}
    for r in selected:
        if r["status"] == "observed":
            value = r["vas"]
            if value is None or not math.isfinite(value) or not 0 <= value <= 10:
                raise ValueError("Invalid observed VAS")
            values[r["time_min"]] = value
    changes = [values[t + 1] - values[t] for t in sorted(values) if t + 1 in values]
    mean_change = statistics.mean(changes) if changes else None
    mssd = statistics.mean(v * v for v in changes) if changes else None
    return dict(
        start_min=start,
        end_min=end,
        n_observed=len(values),
        n_pairs=len(changes),
        complete=all(t in values for t in range(start, end + 1)),
        eligible=len(changes) >= 3,
        mean_vas=statistics.mean(values.values()) if values else None,
        sample_sd=statistics.stdev(values.values()) if len(values) >= 2 else None,
        mssd=mssd,
        rmssd=math.sqrt(mssd) if mssd is not None else None,
        mean_adjacent_change=mean_change,
        centered_change_ms=statistics.mean((v - mean_change) ** 2 for v in changes)
        if changes
        else None,
    )
