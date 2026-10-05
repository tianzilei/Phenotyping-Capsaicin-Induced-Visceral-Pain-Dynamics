"""Observed-support finite changes and recorded-code descriptive proportions."""

from __future__ import annotations
import hashlib
import io
import json
import numpy as np


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def finite_design(values, hs=(1, 2, 5)):
    values = np.asarray(values, float)
    n, minutes = values.shape
    support = []
    change = []
    metadata = []
    for h in hs:
        if not isinstance(h, int) or h < 1 or h >= minutes:
            raise ValueError("Invalid interval length")
        for t in range(minutes - h):
            valid = np.isfinite(values[:, t : t + h + 1]).all(axis=1)
            d = np.full(n, np.nan)
            d[valid] = values[valid, t + h] - values[valid, t]
            support.append(valid)
            change.append(d)
            metadata.append(
                dict(
                    start_minute=t + 1,
                    end_minute=t + h + 1,
                    h_minutes=h,
                    people=int(valid.sum()),
                )
            )
    return np.asarray(support), np.asarray(change), metadata


def evaluate(stage, prepared, weights):
    weights = np.asarray(weights)
    if (
        weights.ndim != 2
        or np.any(weights < 0)
        or not np.all(weights == weights.astype(int))
    ):
        raise ValueError("Expected nonnegative whole-person multiplicities")
    if stage == "symptoms":
        numerator = weights @ prepared["numerator"].T
        denominator = weights @ prepared["denominator"].T
        return np.divide(
            numerator,
            denominator,
            out=np.full(numerator.shape, np.nan),
            where=denominator > 0,
        )
    if stage != "finite_changes":
        raise ValueError("Unknown stage")
    support = prepared["support"]
    change = prepared["change"]
    hs = prepared["h"]
    columns = []
    for valid, d, h in zip(support, change, hs):
        if not np.any(valid):
            columns.extend([np.full(len(weights), np.nan)] * 7)
            continue
        indices = np.flatnonzero(valid)
        local = weights[:, indices]
        delta = d[indices]
        denominator = local.sum(axis=1)
        mean = np.divide(
            local @ delta,
            denominator,
            out=np.full(len(weights), np.nan),
            where=denominator > 0,
        )
        order = np.argsort(delta, kind="stable")
        cdf = local[:, order].cumsum(axis=1)
        rank = np.ceil(0.5 * denominator).astype(int)
        where = (cdf >= rank[:, None]).argmax(axis=1)
        median = np.where(denominator > 0, delta[order[where]], np.nan)
        proportions = [
            np.divide(
                local @ (delta > 0),
                denominator,
                out=np.full(len(weights), np.nan),
                where=denominator > 0,
            ),
            np.divide(
                local @ (delta < 0),
                denominator,
                out=np.full(len(weights), np.nan),
                where=denominator > 0,
            ),
            np.divide(
                local @ (delta == 0),
                denominator,
                out=np.full(len(weights), np.nan),
                where=denominator > 0,
            ),
        ]
        columns.extend([mean, median, mean / h, median / h, *proportions])
    return np.column_stack(columns)


def execute_batch(config, prepared, stage, start, stop):
    from threadpoolctl import threadpool_limits
    import platform
    import time

    begun = time.monotonic()
    n = config["expected_people"]
    weights = []
    hasher = hashlib.sha256()
    with threadpool_limits(limits=1):
        for rep in range(start, stop):
            raw = hashlib.sha256(
                f"{config['master_seed']}|{stage}|{rep}".encode()
            ).digest()
            rng = np.random.default_rng(
                np.random.SeedSequence(np.frombuffer(raw, dtype="<u4").tolist())
            )
            indices = rng.integers(0, n, n)
            hasher.update(indices.astype("<i8").tobytes())
            weights.append(np.bincount(indices, minlength=n))
        values = evaluate(stage, prepared, np.asarray(weights))
    buffer = io.BytesIO()
    np.savez_compressed(buffer, values=values)
    return dict(
        stage=stage,
        start=start,
        stop=stop,
        values_shape=list(values.shape),
        logical_values_sha256=hashlib.sha256(
            values.astype("<f8").tobytes()
        ).hexdigest(),
        subject_indices_sha256=hasher.hexdigest(),
        blob=buffer.getvalue(),
        host=platform.node(),
        seconds=time.monotonic() - begun,
    )
