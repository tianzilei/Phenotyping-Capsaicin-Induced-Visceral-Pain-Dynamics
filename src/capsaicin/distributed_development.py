"""Synthetic derivative development; no real data or scientific acceptance gate."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time

import numpy as np
from threadpoolctl import threadpool_limits


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def environment(lock_text):
    import psutil
    from packaging.requirements import Requirement

    issues, packages = [], {}
    for raw in lock_text.splitlines():
        line = raw.strip().removesuffix("\\").strip()
        if not line or line.startswith(("#", "--")):
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            actual = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        packages[requirement.name] = actual
        if actual is None or not requirement.specifier.contains(actual):
            issues.append(requirement.name)
    if platform.python_version() != "3.12.13":
        issues.append("python")
    return dict(
        python=platform.python_version(),
        executable=sys.executable,
        platform=platform.platform(),
        packages=packages,
        issues=issues,
        physical_cores=psutil.cpu_count(logical=False) or 1,
        memory_total=psutil.virtual_memory().total,
        thread_environment={
            k: os.environ.get(k)
            for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
    )


def generate(config, cell, stage, replicate):
    seed_key = [config["master_seed"], "D", stage, cell["id"], replicate, "data"]
    seed_hex = hashlib.sha256(canonical(seed_key)).hexdigest()
    rng = np.random.default_rng(
        np.random.SeedSequence(
            np.frombuffer(bytes.fromhex(seed_hex), dtype="<u4").tolist()
        )
    )
    n, end = cell["subjects"], cell["end_minute"]
    grid = np.arange(1.0, end + 1)
    scenario = cell["scenario"]
    if scenario == "flat_complete":
        mu, analytic = np.full(end, 4.0), np.zeros(end)
    elif scenario == "linear_random_missing":
        mu, analytic = 2 + 0.15 * grid, np.full(end, 0.15)
    elif scenario == "wave_dropout":
        mu = 4 + np.sin(2 * np.pi * (grid - 1) / 19)
        analytic = 2 * np.pi / 19 * np.cos(2 * np.pi * (grid - 1) / 19)
    elif scenario in (
        "curved_dropout",
        "curved_complete",
        "heteroskedastic_complete",
        "heavy_tailed_complete",
        "informative_dropout",
    ):
        mu, analytic = 2 + 0.5 * grid - 0.02 * grid**2, 0.5 - 0.04 * grid
    else:
        raise ValueError(f"Unknown frozen scenario: {scenario}")
    dgp = config["dgp"]
    burn = dgp["burn_in"]
    total = end + burn
    if scenario == "heavy_tailed_complete":
        innovations = rng.standard_t(dgp["heavy_tail_df"], (n, total))
        innovations *= dgp["innovation_sd"] / np.sqrt(
            dgp["heavy_tail_df"] / (dgp["heavy_tail_df"] - 2)
        )
    else:
        innovations = rng.normal(0, dgp["innovation_sd"], (n, total))
    if scenario == "heteroskedastic_complete":
        innovations[:, burn:] *= 0.5 + grid / end
    errors = np.zeros((n, total))
    for j in range(total):
        errors[:, j] = innovations[:, j] + (dgp["ar"] * errors[:, j - 1] if j else 0)
    y = mu + rng.normal(0, dgp["intercept_sd"], (n, 1)) + errors[:, burn:]
    keep = np.ones((n, end), dtype=bool)
    if scenario == "linear_random_missing":
        keep = rng.random((n, end)) >= dgp["independent_missing_probability"]
    elif scenario in ("curved_dropout", "wave_dropout"):
        stops = rng.integers(12, 21, size=n)
        keep = grid <= stops[:, None]
    elif scenario == "informative_dropout":
        for i in range(n):
            stops = np.flatnonzero((grid > 10) & (y[i] < 4))
            if len(stops):
                keep[i, stops[0] + 1 :] = False
    ids = np.broadcast_to(np.arange(n)[:, None], (n, end))[keep]
    times = np.broadcast_to(grid, (n, end))[keep]
    means = np.broadcast_to(mu, (n, end))[keep]
    values = y[keep]
    h = hashlib.sha256()
    for a in (ids, times, values, means):
        h.update(canonical(list(a.shape)))
        h.update(np.asarray(a, dtype="<f8").tobytes())
    return dict(
        ids=ids,
        times=times,
        values=values,
        means=means,
        analytic=analytic,
        seed_hex=seed_hex,
        input_sha256=h.hexdigest(),
    )


def execute(config, cell, stage, replicate):
    """One logical replicate; expected fitting failures remain in the denominator."""
    # Injected only into the immutable worker bundle; local tests use the real module.
    from .derivative_v5 import basis, fit_derivative
    import psutil

    start = time.monotonic()
    with threadpool_limits(limits=1):
        data = generate(config, cell, stage, replicate)
        result = dict(
            cell=cell["id"],
            stage=stage,
            replicate=replicate,
            config_sha256=digest(config),
            input_sha256=data["input_sha256"],
            seed_hex=data["seed_hex"],
            success=False,
            projection_covered=False,
            analytic_covered=False,
            flat_rejected=False,
            truth_role=cell["truth_role"],
        )
        x, _ = basis(data["times"], (1, cell["end_minute"]), config["coefficients"])
        grid = np.arange(1.0, cell["end_minute"] + 1)
        _, derivative = basis(grid, (1, cell["end_minute"]), config["coefficients"])
        result.update(
            design_rank=int(np.linalg.matrix_rank(x)),
            design_condition=float(np.linalg.cond(x)),
            normal_condition=float(np.linalg.cond(x.T @ x)),
            support=[int(np.sum(data["times"] == t)) for t in grid],
            observed_rows=len(data["times"]),
            outside_scale=int(np.sum((data["values"] < 0) | (data["values"] > 10))),
        )
        try:
            fit = fit_derivative(
                data["ids"],
                data["times"],
                data["values"],
                (1, cell["end_minute"]),
                coefficients=config["coefficients"],
                alpha=config["alpha"],
                minimum_subjects=config["minimum_subjects"],
                minimum_support=config["minimum_support"],
            )
            # Equal observed rows, using the exact realized design of the estimator.
            truth = derivative @ np.linalg.solve(x.T @ x, x.T @ data["means"])
            lower, upper = fit["lower"], fit["upper"]
            projected = (lower <= truth) & (truth <= upper)
            analytic = (lower <= data["analytic"]) & (data["analytic"] <= upper)
            result.update(
                success=True,
                projection_covered=bool(projected.all()),
                analytic_covered=bool(analytic.all()),
                flat_rejected=bool(np.any((lower > 0) | (upper < 0))),
                estimate=fit["estimate"].tolist(),
                se=fit["se"].tolist(),
                lower=lower.tolist(),
                upper=upper.tolist(),
                truth=truth.tolist(),
                analytic_truth=data["analytic"].tolist(),
                projection_bias=(fit["estimate"] - truth).tolist(),
                analytic_bias=(fit["estimate"] - data["analytic"]).tolist(),
                mean_width=float(np.mean(upper - lower)),
                boundary_width=float(np.mean((upper - lower)[[0, -1]])),
                boundary_covered=bool(projected[[0, -1]].all()),
                interior_covered=bool(projected[1:-1].all()),
                boundary_se=float(np.mean(fit["se"][[0, -1]])),
            )
        except (ValueError, np.linalg.LinAlgError) as exc:
            result.update(failure_type=type(exc).__name__, failure_reason=str(exc))
    # Host/runtime fields are deliberately outside the reproducible scientific payload.
    return dict(
        payload=result,
        payload_sha256=digest(result),
        execution=dict(
            host=platform.node(),
            pid=os.getpid(),
            seconds=time.monotonic() - start,
            rss_bytes=psutil.Process().memory_info().rss,
        ),
    )


def execute_serial(config, tasks):
    return [execute(config, cell, stage, replicate) for cell, stage, replicate in tasks]
