"""New fixed-basis estimator, distinct from historical CAR1 GAMM derivatives."""

import numpy as np
from scipy.interpolate import BSpline
from scipy.stats import t


def basis(time, boundaries, coefficients=10):
    lo, hi = boundaries
    values = np.asarray(time, dtype=float)
    if (
        hi <= lo
        or np.any(~np.isfinite(values))
        or np.any((values < lo) | (values > hi))
    ):
        raise ValueError("Time outside fixed boundaries")
    if coefficients < 4 or coefficients > int(hi - lo + 1):
        raise ValueError("Unsupported coefficient count")
    interior = np.linspace(lo, hi, coefficients - 2)[1:-1]
    knots = np.r_[np.repeat(lo, 4), interior, np.repeat(hi, 4)]
    spline = BSpline(knots, np.eye(coefficients), 3, extrapolate=False)
    return spline(values), spline.derivative()(values)


def fit_derivative(
    subjects,
    times,
    values,
    boundaries,
    coefficients=10,
    alpha=0.05,
    minimum_subjects=20,
    minimum_support=10,
):
    ids = np.asarray(subjects)
    times, values = np.asarray(times, float), np.asarray(values, float)
    if (
        ids.ndim != 1
        or times.ndim != 1
        or values.ndim != 1
        or not (len(ids) == len(times) == len(values))
    ):
        raise ValueError("Aligned vectors required")
    if np.any(~np.isfinite(values)) or not 0 < alpha < 1:
        raise ValueError("Finite observed values and valid alpha required")
    unique = np.unique(ids)
    if len(unique) < minimum_subjects:
        raise ValueError("Insufficient independent subjects")
    if len(set(zip(ids.tolist(), times.tolist()))) != len(times):
        raise ValueError("Duplicate subject-minute")
    grid = np.arange(boundaries[0], boundaries[1] + 1, dtype=float)
    support = np.array([len(np.unique(ids[times == g])) for g in grid])
    if np.any(support < minimum_support):
        raise ValueError("Insufficient support at frozen minute grid")
    x, _ = basis(times, boundaries, coefficients)
    _, derivative = basis(grid, boundaries, coefficients)
    groups = [
        (x[ids == s].T @ x[ids == s], x[ids == s].T @ values[ids == s]) for s in unique
    ]
    xx = sum(v[0] for v in groups)
    xy = sum(v[1] for v in groups)
    if np.linalg.matrix_rank(xx) != coefficients:
        raise ValueError("Rank deficient full fit")
    beta = np.linalg.solve(xx, xy)
    deleted = []
    for a, b in groups:
        if np.linalg.matrix_rank(xx - a) != coefficients:
            raise ValueError("Rank deficient deleted-subject fit")
        deleted.append(np.linalg.solve(xx - a, xy - b))
    deleted = np.array(deleted)
    deviations = deleted - deleted.mean(axis=0)
    covariance = (len(unique) - 1) / len(unique) * deviations.T @ deviations
    estimate = derivative @ beta
    se = np.sqrt(
        np.maximum(0, np.einsum("ij,jk,ik->i", derivative, covariance, derivative))
    )
    critical = t.ppf(1 - alpha / (2 * len(grid)), len(unique) - 1)
    return {
        "grid": grid,
        "estimate": estimate,
        "se": se,
        "lower": estimate - critical * se,
        "upper": estimate + critical * se,
        "critical": float(critical),
        "subjects": len(unique),
        "support": support,
        "beta": beta,
        "covariance": covariance,
    }
