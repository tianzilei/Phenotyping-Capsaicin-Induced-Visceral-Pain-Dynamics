"""Whole-person observation and paired fixed-OOF empirical resampling."""

from __future__ import annotations

import hashlib
import math
import numpy as np
from scipy.stats import binom
from threadpoolctl import threadpool_limits


def tokens_to_arrays(tokens):
    """Read the 1..20 minute grid with original missing/termination semantics."""
    values = np.full((len(tokens), 20), np.nan)
    events = np.full((len(tokens), 2), 21, dtype=int)
    for i, row in enumerate(tokens):
        if len(row) != 20:
            raise ValueError("Expected actual minute grid 1..20")
        stopped = None
        for j, raw in enumerate(row):
            text = str(raw).strip()
            if text in ("E", "T"):
                column = 0 if text == "E" else 1
                events[i, column] = min(events[i, column], j + 1)
                if stopped and stopped != text:
                    raise ValueError("Mixed termination markers")
                stopped = text
            elif text == "":
                continue
            else:
                try:
                    number = float(text)
                except ValueError as exc:
                    raise ValueError("Unknown scoring token") from exc
                if not math.isfinite(number) or not 0 <= number <= 10:
                    raise ValueError("Invalid VAS value")
                if stopped:
                    raise ValueError("Numeric observation after termination")
                values[i, j] = number
    return values, events


def index_stream(seed, stage, replicate, n):
    key = f"{seed}|{stage}|{replicate}|subject_multiplicity".encode()
    h = hashlib.sha256(key).digest()
    rng = np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(h, dtype="<u4").tolist())
    )
    index = rng.integers(0, n, size=n)
    return np.bincount(index, minlength=n), hashlib.sha256(
        index.astype("<i8").tobytes()
    ).hexdigest()


def observation_statistics(values, events, weights):
    numeric = np.isfinite(values)
    denominator = weights @ numeric
    # Zeros below are masked additive identities, never imputed observations.
    numerator = weights @ np.where(numeric, values, 0.0)
    means = np.divide(
        numerator, denominator, out=np.full(20, np.nan), where=denominator > 0
    )
    minutes = np.arange(1, 21)
    fractions = denominator / weights.sum()
    e = (weights @ (events[:, 0, None] <= minutes)) / weights.sum()
    t = (weights @ (events[:, 1, None] <= minutes)) / weights.sum()
    return np.r_[means, fractions, e, t]


def prediction_statistics(prepared, weights, person_equal=False):
    counts, absolute, squared = prepared
    if person_equal:
        mae = (weights @ (absolute / counts[:, None])) / weights.sum()
        mse = (weights @ (squared / counts[:, None])) / weights.sum()
    else:
        denominator = weights @ counts
        mae = (weights @ absolute) / denominator
        mse = (weights @ squared) / denominator
    rmse = np.sqrt(mse)
    return np.r_[mae, rmse, mae[1:] - mae[0], rmse[1:] - rmse[0]]


def bootstrap_batch(config, prepared, stage, start, stop):
    from .distributed_development import digest
    import os
    import platform
    import time
    import psutil

    started = time.monotonic()
    rows, index_hashes = [], []
    n = len(prepared[0])
    with threadpool_limits(limits=1):
        for replicate in range(start, stop):
            w, h = index_stream(config["master_seed"], stage, replicate, n)
            index_hashes.append(h)
            if stage == "VAS_observation":
                row = observation_statistics(*prepared, w)
            else:
                row = prediction_statistics(prepared, w)
                if stage == "next_rating":
                    row = np.r_[
                        row, prediction_statistics(prepared, w, person_equal=True)
                    ]
            rows.append([float(x) if np.isfinite(x) else None for x in row])
    if stage == "VAS_observation":
        point = observation_statistics(*prepared, np.ones(n, dtype=int))
    else:
        point = prediction_statistics(prepared, np.ones(n, dtype=int))
        if stage == "next_rating":
            point = np.r_[
                point,
                prediction_statistics(
                    prepared, np.ones(n, dtype=int), person_equal=True
                ),
            ]
    payload = dict(
        stage=stage,
        start=start,
        stop=stop,
        statistics=rows,
        point=[float(x) if np.isfinite(x) else None for x in point],
        index_sha256=index_hashes,
        config_sha256=digest(config),
        input_sha256=config["prepared_input_sha256"][stage],
    )
    return dict(
        payload=payload,
        payload_sha256=digest(payload),
        execution=dict(
            host=platform.node(),
            pid=os.getpid(),
            seconds=time.monotonic() - started,
            rss_bytes=psutil.Process().memory_info().rss,
        ),
    )


def rank_interval(b, probability, gamma):
    """Exact binomial rank endpoints, including sentinel ranks 0 and B+1."""
    if b < 1 or not 0 < probability < 1 or not 0 < gamma < 1:
        raise ValueError("Invalid rank interval parameters")
    low, high = 0, b
    while low < high:
        mid = (low + high + 1) // 2
        if binom.cdf(mid - 1, b, probability) <= gamma / 2:
            low = mid
        else:
            high = mid - 1
    r = low
    low, high = 1, b + 1
    while low < high:
        mid = (low + high) // 2
        if binom.sf(mid - 1, b, probability) <= gamma / 2:
            high = mid
        else:
            low = mid + 1
    return r, low


def endpoint(values, probability, gamma, known_bounds):
    ordered = np.sort(values)
    b = len(ordered)
    r, s = rank_interval(b, probability, gamma)
    estimate = float(ordered[max(0, math.ceil(b * probability) - 1)])
    lo = float(ordered[r - 1]) if r else known_bounds[0]
    hi = float(ordered[s - 1]) if s <= b else known_bounds[1]
    if lo is None or hi is None:
        half_width = None
    else:
        half_width = max(estimate - lo, hi - estimate)
    return dict(
        estimate=estimate,
        lower_MC=lo,
        upper_MC=hi,
        lower_rank=r,
        upper_rank=s,
        MC_half_width=half_width,
    )


def summarize_column(values, config, bounds, unit):
    valid = values[np.isfinite(values)]
    if not len(valid):
        return dict(status="UNDEFINED_SUPPORT", attempted=len(values), valid=0)
    gamma = config["MC_total_error_probability"] / (2 * config["statistic_family_size"])
    lower, upper = [endpoint(valid, p, gamma, bounds) for p in (0.025, 0.975)]
    width = upper["estimate"] - lower["estimate"]
    widths = [lower["MC_half_width"], upper["MC_half_width"]]
    mc = max(widths) if all(x is not None for x in widths) else None
    relative = mc is not None and (mc <= 0.02 * width if width else mc == 0)
    absolute = mc is not None and mc <= (0.002 if unit == "proportion" else 0.01)
    return dict(
        attempted=len(values),
        valid=len(valid),
        undefined=len(values) - len(valid),
        lower=lower,
        upper=upper,
        empirical_range_width=width,
        zero_width=width == 0,
        MC_max_endpoint_half_width=mc,
        gamma_per_endpoint=gamma,
        status="MC_PRECISION_MET"
        if relative and absolute
        else "MC_PRECISION_INSUFFICIENT",
        uncertainty_role="descriptive_empirical_resampling_not_population_coverage",
    )
