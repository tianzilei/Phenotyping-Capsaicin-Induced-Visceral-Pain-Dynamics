"""SNIRF time-vector semantics, without inferring physical units."""

import math


def expand_snirf_time(values, sample_count):
    values = [float(x) for x in values]
    if sample_count < 1 or not values or any(not math.isfinite(x) for x in values):
        raise ValueError("Invalid signal time metadata")
    if len(values) == 2 and sample_count != 2:
        start, step = values
        if step <= 0:
            raise ValueError("Nonpositive compressed time step")
        values = [start + i * step for i in range(sample_count)]
    if len(values) != sample_count:
        raise ValueError("Time length does not match samples")
    if any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError("Non-increasing signal time")
    return values
