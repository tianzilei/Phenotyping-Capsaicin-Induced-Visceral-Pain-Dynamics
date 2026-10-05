"""Observed person-level variability and complete-interval burden resampling."""

from __future__ import annotations

import numpy as np
from .variability import window_metrics


RAW = (
    "mean_vas",
    "sample_sd",
    "mssd",
    "rmssd",
    "mean_adjacent_change",
    "centered_change_ms",
)


def residual_metrics(t, y, degree):
    t, y = np.asarray(t, float), np.asarray(y, float)
    if len(t) != len(y) or len(np.unique(t)) != len(t) or not np.isfinite(y).all():
        raise ValueError("Invalid residual series")
    order = np.argsort(t)
    t, y = t[order], y[order]
    x = (t - t.mean())[:, None] ** np.arange(degree + 1)
    coef, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    if rank != degree + 1 or len(y) <= degree + 1:
        raise ValueError("Insufficient trend rank")
    e = y - x @ coef
    adjacent = np.diff(t) == 1
    return [
        float(e @ e / (len(y) - degree - 1)),
        float(np.mean(np.diff(e)[adjacent] ** 2)) if adjacent.any() else np.nan,
        float(np.mean(np.diff(y)[adjacent] ** 2)) if adjacent.any() else np.nan,
    ]


def segment_integrals(t, y):
    t, y = np.asarray(t, float), np.asarray(y, float)
    a, h, v, d = t[:-1], np.diff(t), y[:-1], np.diff(y)
    return float(np.sum(h * (v + d / 2))), float(
        np.sum(h * (a * v + (a * d + h * v) / 2 + h * d / 3))
    )


def burden_metrics(t, y):
    t, y = np.asarray(t, float), np.asarray(y, float)
    if (
        len(t) != len(y)
        or len(t) < 2
        or not np.all(np.diff(t) == 1)
        or not np.isfinite(y).all()
        or np.any(y < 0)
    ):
        raise ValueError("Complete consecutive nonnegative series required")
    area, moment = segment_integrals(t, y)
    mid = (t[0] + t[-1]) / 2
    late_t = np.unique(np.r_[mid, t[t > mid]])
    late_area, _ = segment_integrals(late_t, np.interp(late_t, t, y))
    return [
        area,
        moment / area if area > 0 else np.nan,
        late_area / area if area > 0 else np.nan,
    ]


def specifications(config):
    specs = []
    raw_bounds = ([0, 10], [0, 10], [0, 100], [0, 10], [-10, 10], [0, 100])
    raw_units = ("VAS", "VAS", "VAS_squared", "VAS", "VAS", "VAS_squared")

    def add(name, bounds, unit, aggregation="median"):
        specs.append(
            dict(
                statistic=name,
                bounds=list(bounds),
                unit=unit,
                aggregation=aggregation,
                MC_absolute_tolerance=config["MC_absolute_tolerance"][unit],
            )
        )

    for a, b in config["windows"]:
        for policy in ("at_least_3_pairs", "complete_window"):
            for metric, bounds, unit in zip(RAW, raw_bounds, raw_units):
                add(f"raw_{a}_{b}_{policy}_{metric}", bounds, unit)
    for metric, bounds, unit in zip(RAW, raw_bounds, raw_units):
        add(
            "paired_16_20_minus_1_5_" + metric,
            [bounds[0] - bounds[1], bounds[1] - bounds[0]],
            unit,
            "mean",
        )
    for a, b in config["intervals"]:
        for degree in config["residual"]["degrees"]:
            for metric in ("residual_variance", "residual_mssd", "raw_mssd"):
                add(
                    f"residual_{a}_{b}_degree{degree}_{metric}",
                    [0, None],
                    "VAS_squared",
                )
        for metric, bounds, unit in [
            ("auc", [0, 10 * (b - a)], "VAS_minutes"),
            ("time_centroid", [a, b], "minutes"),
            ("late_area_fraction", [0, 1], "proportion"),
        ]:
            add(f"burden_{a}_{b}_{metric}", bounds, unit)
    return specs


def prepare_matrix(values, config):
    if (
        values.ndim != 2
        or values.shape[1] != 20
        or np.isinf(values).any()
        or np.any(values[np.isfinite(values)] < 0)
        or np.any(values[np.isfinite(values)] > 10)
    ):
        raise ValueError("Expected finite-or-missing 1..20 VAS")
    specs = specifications(config)
    matrix = np.full((len(values), len(specs)), np.nan)
    for i, y in enumerate(values):
        rows = [
            dict(
                time_min=j + 1,
                status="observed" if np.isfinite(v) else "missing",
                vas=float(v) if np.isfinite(v) else None,
            )
            for j, v in enumerate(y)
        ]
        windows = {}
        cells = []
        for a, b in config["windows"]:
            m = window_metrics(rows, a, b)
            windows[a, b] = m
            for eligible in (m["eligible"], m["complete"]):
                cells.extend(
                    [m[k] if eligible and m[k] is not None else np.nan for k in RAW]
                )
        early, late = windows[1, 5], windows[16, 20]
        cells.extend(
            [
                late[k] - early[k] if early["complete"] and late["complete"] else np.nan
                for k in RAW
            ]
        )
        for a, b in config["intervals"]:
            t = np.arange(a, b + 1)
            z = y[a - 1 : b]
            valid = np.isfinite(z)
            eligible = (
                valid.sum() >= config["residual"]["minimum_points"]
                and np.sum(valid[:-1] & valid[1:])
                >= config["residual"]["minimum_adjacent_pairs"]
            )
            for degree in config["residual"]["degrees"]:
                cells.extend(
                    residual_metrics(t[valid], z[valid], degree)
                    if eligible
                    else [np.nan] * 3
                )
            cells.extend(burden_metrics(t, z) if valid.all() else [np.nan] * 3)
        matrix[i] = cells
    return matrix


def weighted_statistics(matrix, weights, specs):
    """Exact median of expanded person copies, including even-sample averaging."""
    matrix, weights = np.asarray(matrix), np.asarray(weights)
    if (
        weights.shape != (len(matrix),)
        or np.any(weights < 0)
        or np.any(weights != weights.astype(int))
    ):
        raise ValueError("Nonnegative integer person multiplicities required")
    finite = np.isfinite(matrix)
    counts = weights @ finite
    order = np.argsort(matrix, axis=0, kind="stable")
    ordered = np.take_along_axis(matrix, order, axis=0)
    cumulative = np.cumsum(
        weights[order] * np.take_along_axis(finite, order, axis=0), axis=0
    )
    lo = (counts + 1) // 2
    hi = counts // 2 + 1
    left = np.argmax(cumulative >= lo, axis=0)
    right = np.argmax(cumulative >= hi, axis=0)
    columns = np.arange(matrix.shape[1])
    result = (ordered[left, columns] + ordered[right, columns]) / 2
    result[counts == 0] = np.nan
    means = np.asarray([s["aggregation"] == "mean" for s in specs])
    numerator = weights @ np.where(finite, matrix, 0.0)
    result[means] = np.divide(
        numerator[means],
        counts[means],
        out=np.full(means.sum(), np.nan),
        where=counts[means] > 0,
    )
    return result, counts


def bootstrap_batch(config, prepared, stage, start, stop):
    from .distributed_observation import index_stream
    from .distributed_development import digest
    from threadpoolctl import threadpool_limits
    import os
    import platform
    import time
    import psutil

    begun = time.monotonic()
    matrix = prepared[0]
    specs = specifications(config)
    statistics, hashes, supports = [], [], []
    with threadpool_limits(limits=1):
        for replicate in range(start, stop):
            w, h = index_stream(config["master_seed"], stage, replicate, len(matrix))
            row, count = weighted_statistics(matrix, w, specs)
            statistics.append([float(v) if np.isfinite(v) else None for v in row])
            hashes.append(h)
            supports.append(count)
        point, count = weighted_statistics(
            matrix, np.ones(len(matrix), dtype=int), specs
        )
    payload = dict(
        stage=stage,
        start=start,
        stop=stop,
        statistics=statistics,
        index_sha256=hashes,
        point=[float(v) if np.isfinite(v) else None for v in point],
        original_eligible_counts=count.tolist(),
        resampled_support_min=np.min(supports, axis=0).tolist(),
        resampled_support_max=np.max(supports, axis=0).tolist(),
        config_sha256=digest(config),
        input_sha256=config["prepared_input_sha256"][stage],
    )
    return dict(
        payload=payload,
        payload_sha256=digest(payload),
        execution=dict(
            host=platform.node(),
            pid=os.getpid(),
            seconds=time.monotonic() - begun,
            rss_bytes=psutil.Process().memory_info().rss,
        ),
    )
