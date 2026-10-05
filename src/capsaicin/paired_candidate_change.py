"""Development-pair summaries for neutral ECG/EGG candidate features."""

from __future__ import annotations
import numpy as np
from scipy import stats


def strict_pair(rows, baseline_stages=("N", "C", "P"), stimulus_stage="E"):
    groups = {}
    for row in rows:
        key = (row["subject_id"], row["recording_stem"])
        stage = row["stage"]
        if stage in groups.setdefault(key, {}):
            raise ValueError("duplicate stage")
        groups[key][stage] = row
    result = []
    for key, stages in sorted(groups.items()):
        base = next((stage for stage in baseline_stages if stage in stages), None)
        if base is None or stimulus_stage not in stages:
            raise ValueError("strict pair missing")
        result.append((key, base, stages[base], stages[stimulus_stage]))
    return result


def bootstrap_median_interval(values, seed=20260929, replicates=5000, alpha=0.05):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return None
    rng = np.random.default_rng(seed)
    draws = np.median(
        values[rng.integers(0, len(values), size=(replicates, len(values)))], axis=1
    )
    return {
        "median": float(np.median(values)),
        "bootstrap_descriptive_low": float(np.quantile(draws, alpha / 2)),
        "bootstrap_descriptive_high": float(np.quantile(draws, 1 - alpha / 2)),
    }


def rank_change_summary(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return {
            "spearman_rho": None,
            "leave_one_out_min": None,
            "leave_one_out_max": None,
        }
    rho = float(stats.spearmanr(x, y).statistic)
    loo = []
    for i in range(len(x)):
        value = stats.spearmanr(np.delete(x, i), np.delete(y, i)).statistic
        if np.isfinite(value):
            loo.append(float(value))
    return {
        "spearman_rho": rho,
        "leave_one_out_min": min(loo) if loo else None,
        "leave_one_out_max": max(loo) if loo else None,
    }
