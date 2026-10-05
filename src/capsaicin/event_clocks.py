"""Read event clock values without creating a synchronized or clinical timeline."""

import math


def finite_number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def hms_seconds(value):
    parts = value.strip().split(":")
    if len(parts) != 3:
        raise ValueError("Expected HH:MM:SS label")
    h, m, s = (finite_number(v) for v in parts)
    if (
        any(v is None for v in (h, m, s))
        or h < 0
        or h != int(h)
        or not 0 <= m < 60
        or m != int(m)
        or not 0 <= s < 60
    ):
        raise ValueError("Invalid HH:MM:SS label")
    return h * 3600 + m * 60 + s


def observed_intervals(rows, field):
    """Retain row support: these are observed-event gaps, not adjacent-minute metrics."""
    previous = None
    result = []
    for row_number, row in enumerate(rows, 2):
        value = finite_number(row.get(field))
        if value is None:
            continue
        if previous is not None:
            result.append(
                dict(
                    field=field,
                    previous_csv_row=previous[0],
                    csv_row=row_number,
                    interval_native=value - previous[1],
                    intervening_csv_rows=row_number - previous[0] - 1,
                )
            )
        previous = (row_number, value)
    return result


def digital_pulses(edges):
    """No sorting: acquisition order and discontinuities remain visible."""
    result = []
    for a, b in zip(edges, edges[1:]):
        before, high, next_before, after = (
            float(v)
            for v in (
                a["previous_native"],
                a["next_native"],
                b["previous_native"],
                b["next_native"],
            )
        )
        start, stop = (
            float(a["time_from_recording_start_s"]),
            float(b["time_from_recording_start_s"]),
        )
        if high > before and next_before == high and after == before and stop > start:
            result.append(
                dict(
                    start_s=start,
                    stop_s=stop,
                    duration_s=stop - start,
                    initial_native=before,
                    excursion_native=high,
                )
            )
    return result
