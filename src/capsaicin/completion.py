"""Actual-time and person-level contracts for exploratory completion analyses."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path


def relative_manifest_path(directory, value):
    """Resolve Windows/POSIX relative manifest paths without guessing filenames."""
    normalized = str(value).replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute() or ":" in normalized or ".." in path.parts:
        raise ValueError("Manifest output must be a confined relative path")
    return Path(directory) / path


def numeric_trajectory(rows, end):
    """Preserve missing markers; never fabricate complete trajectories."""
    values = (
        rows[[f"VAS_{m}min" for m in range(1, end + 1)]]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy(float)
    )
    valid = np.isfinite(values).all(axis=1)
    if np.any(np.isfinite(values) & ((values < 0) | (values > 10))):
        raise ValueError("Numeric VAS outside confirmed scale")
    return values, valid


def post_stop_grid(rows, e_levels, t_levels):
    """Aggregate hypothetical missing scores without exporting imputed people."""
    values = (
        rows[[f"VAS_{m}min" for m in range(1, 21)]]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy(float)
    )
    finite = np.isfinite(values)
    if np.any(finite & ((values < 0) | (values > 10))):
        raise ValueError("Numeric VAS outside confirmed scale")
    n = len(rows)
    if not n:
        raise ValueError("No people")
    counts = {code: np.zeros(20, int) for code in ("E", "T", "other")}
    for tokens, observed in zip(
        rows[[f"VAS_{m}min" for m in range(1, 21)]].to_numpy(), finite
    ):
        prior = "other"
        for m, token in enumerate(tokens):
            text = str(token).strip()
            if text in ("E", "T"):
                prior = text
            elif not observed[m] and text not in ("", "nan", "None"):
                raise ValueError("Unknown VAS token")
            if not observed[m]:
                counts[prior][m] += 1
    total = np.where(finite, values, 0).sum(axis=0)
    lower = total / n
    upper = (total + 10 * (~finite).sum(axis=0)) / n
    curves, areas = [], []
    for e in e_levels:
        for t in t_levels:
            if not 0 <= e <= 10 or not 0 <= t <= 10:
                raise ValueError("Scenario outside confirmed scale")
            base = (total + e * counts["E"] + t * counts["T"]) / n
            high = base + 10 * counts["other"] / n
            for m in range(20):
                curves.append(
                    dict(
                        assumed_E=e,
                        assumed_T=t,
                        time_min=m + 1,
                        n_people=n,
                        n_observed=int(finite[:, m].sum()),
                        n_E_missing=int(counts["E"][m]),
                        n_T_missing=int(counts["T"][m]),
                        n_other_missing=int(counts["other"][m]),
                        hypothetical_mean_low=float(base[m]),
                        hypothetical_mean_high=float(high[m]),
                    )
                )
            areas.append(
                dict(
                    assumed_E=e,
                    assumed_T=t,
                    hypothetical_auc_low=float(np.trapezoid(base)),
                    hypothetical_auc_high=float(np.trapezoid(high)),
                )
            )
    return (
        curves,
        areas,
        dict(
            people=n,
            observed=int(finite.sum()),
            marginal_lower=lower.tolist(),
            marginal_upper=upper.tolist(),
            algebraic_auc_lower=float(np.trapezoid(lower)),
            algebraic_auc_upper=float(np.trapezoid(upper)),
        ),
    )


def shapelet_distances(x, candidates):
    """Distances use only actual consecutive samples in the supplied prefix."""
    x, candidates = np.asarray(x, float), np.asarray(candidates, float)
    if x.ndim != 2 or candidates.ndim != 2 or not len(candidates):
        raise ValueError("Two nonempty matrices required")
    if not np.isfinite(x).all() or not np.isfinite(candidates).all():
        raise ValueError("Shapelet cannot bridge a missing value")
    length = candidates.shape[1]
    if length > x.shape[1]:
        raise ValueError("Shapelet exceeds observed prefix")
    windows = np.lib.stride_tricks.sliding_window_view(x, length, axis=1)
    return np.min(
        np.mean((windows[:, :, None, :] - candidates[None, None, :, :]) ** 2, axis=-1),
        axis=1,
    )


def select_shapelets(x_train, labels, length, maximum_per_class, seed):
    """Fit both candidate sampling and class contrasts on training people only."""
    x_train, labels = np.asarray(x_train, float), np.asarray(labels)
    if not np.isfinite(x_train).all() or len(np.unique(labels)) < 2:
        raise ValueError("Finite training values and at least two classes required")
    rng = np.random.default_rng(seed)
    candidates, origins = [], []
    for label in sorted(np.unique(labels)):
        origins_class = [
            (int(i), start)
            for i in np.flatnonzero(labels == label)
            for start in range(x_train.shape[1] - length + 1)
        ]
        if not origins_class:
            raise ValueError("No consecutive training candidate")
        take = rng.choice(
            len(origins_class),
            min(maximum_per_class, len(origins_class)),
            replace=False,
        )
        for j in take:
            i, start = origins_class[j]
            candidates.append(x_train[i, start : start + length].copy())
            origins.append((i, start, int(label)))
    candidates = np.asarray(candidates)
    distances = shapelet_distances(x_train, candidates)
    selected, details = [], []
    for label in sorted(np.unique(labels)):
        a, b = distances[labels == label], distances[labels != label]
        score = (a.mean(axis=0) - b.mean(axis=0)) ** 2 / (
            a.var(axis=0) + b.var(axis=0) + 1e-12
        )
        # Preserve class-specific provenance rather than reusing another class's segment.
        eligible = np.array([origin[2] == label for origin in origins])
        choice = int(np.argmax(np.where(eligible, score, -np.inf)))
        selected.append(candidates[choice])
        details.append(
            dict(
                training_row=origins[choice][0],
                start_index=origins[choice][1],
                training_class=int(label),
                contrast_score=float(score[choice]),
            )
        )
    return np.asarray(selected), details


def candidate_panel(data, columns, standardized=()):
    """Validate uniqueness and filter finite, repeated observations before fitting."""
    data = data.copy()
    if data.duplicated(["person_id", "block"]).any():
        raise ValueError("Duplicate person/block model input")
    for name in columns:
        data[name] = pd.to_numeric(data[name], errors="coerce")
    data = data[np.isfinite(data[list(columns)]).all(axis=1)].copy()
    counts = data.groupby("person_id").block.nunique()
    data = data[data.person_id.isin(counts[counts >= 2].index)].copy()
    for name in standardized:
        mean = data.groupby("person_id")[name].transform("mean")
        sd = data.groupby("person_id")[name].transform("std")
        data[name] = (data[name] - mean) / sd
    data = data[np.isfinite(data[list(columns)]).all(axis=1)].copy()
    return data.sort_values(["person_id", "block"]).reset_index(drop=True)


def fe_sufficient(data, outcome, predictors):
    """Exact person demeaning and block dummies, with per-person cross-products."""
    if data.duplicated(["person_id", "block"]).any():
        raise ValueError("Duplicate person/block model input")
    if not len(data):
        return None
    people = sorted(data.person_id.unique())
    g = pd.Categorical(data.person_id, categories=people).codes
    z = pd.get_dummies(data.block.astype(int), drop_first=True, dtype=float)
    a = np.column_stack(
        [
            data[outcome].to_numpy(float),
            data[list(predictors)].to_numpy(float),
            z.to_numpy(float),
        ]
    )
    if not np.isfinite(a).all():
        raise ValueError("Nonfinite model data")
    a -= pd.DataFrame(a).groupby(g).transform("mean").to_numpy()
    gram = np.zeros((len(people), a.shape[1], a.shape[1]))
    for i in range(len(people)):
        gram[i] = a[g == i].T @ a[g == i]
    return dict(gram=gram, people=people, n=len(a), p=len(predictors))


def solve_fe(prepared, counts=None):
    """Multiplicity weights equal relabelled person copies in a cluster bootstrap."""
    if prepared is None:
        return None
    gram = prepared["gram"]
    weights = np.ones(len(gram)) if counts is None else np.asarray(counts, float)
    if weights.shape != (len(gram),) or np.any(weights < 0):
        raise ValueError("Invalid person multiplicity weights")
    total = np.einsum("i,ijk->jk", weights, gram)
    xx, xy = total[1:, 1:], total[1:, 0]
    if not len(xx) or np.linalg.matrix_rank(xx) < len(xx):
        return None
    beta = np.linalg.solve(xx, xy)
    sse = max(0.0, float(total[0, 0] - xy @ beta))
    return dict(
        coefficients=beta[: prepared["p"]],
        sse=sse,
        within_outcome_ss=float(total[0, 0]),
        design_rank=len(xx),
    )


def person_bootstrap(prepared, replicates, rng):
    if prepared is None:
        return np.empty((0, 0)), 0
    n = len(prepared["people"])
    coefficients = []
    for _ in range(replicates):
        counts = np.bincount(rng.integers(n, size=n), minlength=n)
        fit = solve_fe(prepared, counts)
        if fit is not None:
            coefficients.append(fit["coefficients"])
    return np.asarray(coefficients).reshape(-1, prepared["p"]), replicates - len(
        coefficients
    )
