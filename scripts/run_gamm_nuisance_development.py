"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
from capsaicin.random_streams import generator
from capsaicin.distributed_r_plan import r_seed

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]


def synthetic_request(config, end, variance, rho, replicate, correlated):
    label = f"T{end}_v{variance}_rho{rho}"
    master = config["master_seed"]
    rng = generator(master, label, replicate, "generation")
    grid = np.arange(1, end + 1)
    n = config["people"]
    mean = 3 + 0.05 * grid + 0.5 * np.sin(np.pi * grid / 20)
    covariance = config["residual_variance"] * np.power(
        rho, np.abs(grid[:, None] - grid[None, :])
    )
    offset = rng.normal(0, np.sqrt(variance), (n, 1))
    noise = rng.normal(size=(n, end)) @ np.linalg.cholesky(covariance).T
    y = mean + offset + noise
    d = dict(person=[], time=[], vas=[])
    for person in range(n):
        keep = ~np.isin(grid, [5, 10]) if person % 5 == 0 else np.ones(end, dtype=bool)
        for t, v in zip(grid[keep], y[person, keep]):
            d["person"].append(f"synthetic_{person:04d}")
            d["time"].append(int(t))
            d["vas"].append(float(v))
    return (
        dict(
            task=f"{label}_r{replicate:03d}_CAR1{int(correlated)}",
            seed=r_seed(master, label, replicate),
            k=6,
            correlated=correlated,
            grid=grid.tolist(),
            data=d,
        ),
        mean,
    )
