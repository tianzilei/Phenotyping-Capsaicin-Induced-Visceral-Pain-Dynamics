"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]


def independent_FPCA(items, rtol=1e-08, atol=1e-08):
    import itertools
    import numpy as np

    differences = dict(cumulative_fve=0.0, angle_deg=0.0, matched_inner=0.0)

    def fit(y, grid):
        if (
            not np.isfinite(y).all()
            or not np.isfinite(grid).all()
            or (not (np.diff(grid) > 0).all())
        ):
            raise ValueError("Invalid FPCA input")
        weights = np.empty(len(grid))
        dt = np.diff(grid)
        weights[0] = dt[0] / 2
        weights[-1] = dt[-1] / 2
        weights[1:-1] = (dt[:-1] + dt[1:]) / 2
        centered = y - y.mean(axis=0)
        singular = np.linalg.svd(centered * np.sqrt(weights), full_matrices=False)
        values = singular[1] ** 2
        if values.sum() <= 1e-12:
            raise ValueError("No between-person variation")
        return (
            np.cumsum(values[:4] / values.sum()),
            singular[2][:4].T / np.sqrt(weights[:, None]),
            weights,
        )

    for request, saved in items:
        y = np.asarray(request["data"]["y"], float)
        grid = np.asarray(request["grid"], float)
        ref_fve, ref, weights = fit(y, grid)
        draw = np.asarray(request["draw"], int)
        if len(draw) != len(y) or np.any(draw < 0) or np.any(draw >= len(y)):
            raise ValueError("Invalid whole-person draw")
        fve, phi, _ = fit(y[draw], grid)
        inner = ref.T @ (weights[:, None] * phi)
        permutations = list(itertools.permutations(range(4)))
        objectives = [
            sum((abs(inner[j, p[j]]) for j in range(4))) for p in permutations
        ]
        perm = permutations[int(np.argmax(objectives))]
        matched = np.asarray([abs(inner[j, perm[j]]) for j in range(4)])
        angles = []
        for k in range(1, 5):
            s = np.linalg.svd(
                ref[:, :k].T @ (weights[:, None] * phi[:, :k]), compute_uv=False
            )
            angles.append(np.degrees(np.arccos(np.clip(s, 0, 1))).max())
        for key, expected in [
            ("cumulative_fve", fve),
            ("angle_deg", angles),
            ("matched_inner", matched),
        ]:
            actual = np.asarray(saved[key], float)
            expected = np.asarray(expected)
            if actual.shape != expected.shape or not np.allclose(
                actual, expected, rtol=rtol, atol=atol
            ):
                raise ValueError("Independent FPCA numerical mismatch: " + key)
            differences[key] = max(
                differences[key], float(np.max(np.abs(actual - expected)))
            )
    return dict(status="PASS", checked=len(items), max_absolute_difference=differences)
