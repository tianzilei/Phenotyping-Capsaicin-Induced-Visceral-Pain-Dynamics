"""E/T stopping descriptions and algebraic bounds without imputed records."""

from collections import Counter, defaultdict
import math
import random

from .contracts import ContractError


def group_series(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["subject_id"]].append(row)
    return {sid: sorted(z, key=lambda r: r["time_min"]) for sid, z in groups.items()}


def audit_stopping(rows, processed_E=False):
    result = []
    for sid, z in group_series(rows).items():
        by_time = {r["time_min"]: r for r in z}
        markers = [r for r in z if r["status"] in ("termination_E", "termination_T")]
        first = markers[0] if markers else None
        code = first["termination_code"] if first else "none"
        t = first["time_min"] if first else None
        obs = [r for r in z if r["status"] == "observed"]
        preceding = [by_time.get(t - 2), by_time.get(t - 1)] if first else [None, None]
        support = "not_applicable"
        if code == "E":
            if any(r is None or r["status"] != "observed" for r in preceding):
                support = "preceding_numeric_window_unavailable"
            elif all(r["vas"] == 0 for r in preceding):
                support = "two_preceding_recorded_zeros"
            else:
                support = "not_two_preceding_recorded_zeros_requires_review"
            if processed_E:
                support = (
                    "remaining_uncoded_zero_pair"
                    if support == "two_preceding_recorded_zeros"
                    else "existing_E_processed_no_preceding_zeros_required"
                )
        pairs = [
            (a, b)
            for a, b in zip(z, z[1:])
            if b["time_min"] - a["time_min"] == 1
            and a["status"] == b["status"] == "observed"
            and a["vas"] == b["vas"] == 0
        ]
        result.append(
            dict(
                subject_id=sid,
                eventual_marker=code,
                first_marker_min=t,
                verified_event_time_min=None,
                n_observed=len(obs),
                last_observed_min=obs[-1]["time_min"] if obs else None,
                last_observed_vas=obs[-1]["vas"] if obs else None,
                preceding_2min_vas=preceding[0]["vas"]
                if preceding[0] and preceding[0]["status"] == "observed"
                else None,
                preceding_1min_vas=preceding[1]["vas"]
                if preceding[1] and preceding[1]["status"] == "observed"
                else None,
                E_recorded_support=support,
                n_observed_adjacent_zero_pairs=len(pairs),
                first_recorded_zero_pair_end_min=pairs[0][1]["time_min"]
                if pairs
                else None,
                individual_stop_reason_verified=False,
            )
        )
    return result


def stopping_distribution(audit, minutes):
    n = len(audit)
    if n == 0:
        raise ContractError("No candidate rows for stopping description")
    result = []
    for t in minutes:
        new = {
            c: sum(
                r["eventual_marker"] == c and r["first_marker_min"] == t for r in audit
            )
            for c in ["E", "T"]
        }
        cumulative = {
            c: sum(
                r["eventual_marker"] == c and r["first_marker_min"] <= t for r in audit
            )
            for c in ["E", "T"]
        }
        result.append(
            dict(
                time_min=t,
                n_candidate=n,
                n_first_E=new["E"],
                n_first_T=new["T"],
                n_E_by_minute=cumulative["E"],
                n_T_by_minute=cumulative["T"],
                fraction_E_by_minute=cumulative["E"] / n,
                fraction_T_by_minute=cumulative["T"] / n,
                n_without_marker_yet=n - cumulative["E"] - cumulative["T"],
            )
        )
    return result


def quantile(values, p):
    if not values:
        return None
    s = sorted(values)
    x = (len(s) - 1) * p
    i = int(x)
    j = min(i + 1, len(s) - 1)
    return s[i] + (s[j] - s[i]) * (x - i)


def observed_bootstrap(
    rows, minutes, replicates, seed, level=0.95, minimum_valid_fraction=0.8
):
    groups = list(group_series(rows).values())
    n = len(groups)
    if (
        not n
        or replicates < 20
        or not 0 < level < 1
        or not 0 < minimum_valid_fraction <= 1
    ):
        raise ContractError("Invalid bootstrap parameters")
    observations = []
    for z in groups:
        observations.append(
            {r["time_min"]: r["vas"] for r in z if r["status"] == "observed"}
        )
    randomizer = random.Random(seed)
    samples = {t: [] for t in minutes}
    # Each draw retains the entire subject's observations and missing pattern.
    for _ in range(replicates):
        weights = Counter(randomizer.randrange(n) for _ in range(n))
        sums = {t: 0.0 for t in minutes}
        counts = {t: 0 for t in minutes}
        for i, w in weights.items():
            for t, v in observations[i].items():
                if t in sums:
                    sums[t] += w * v
                    counts[t] += w
        for t in minutes:
            if counts[t]:
                samples[t].append(sums[t] / counts[t])
    result = []
    alpha = (1 - level) / 2
    for t in minutes:
        vals = [z[t] for z in observations if t in z]
        valid = len(samples[t])
        sufficient = valid >= max(20, minimum_valid_fraction * replicates)
        result.append(
            dict(
                time_min=t,
                n_observed=len(vals),
                mean_observed=sum(vals) / len(vals) if vals else None,
                bootstrap_pointwise_lower=quantile(samples[t], alpha)
                if sufficient
                else None,
                bootstrap_pointwise_upper=quantile(samples[t], 1 - alpha)
                if sufficient
                else None,
                bootstrap_valid=valid,
                bootstrap_without_observations=replicates - valid,
                interval_status="available"
                if sufficient
                else "insufficient_bootstrap_support",
            )
        )
    return result


def bounded_means(rows, minutes, lower, upper):
    if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
        raise ContractError("Invalid scale bounds")
    groups = group_series(rows)
    n = len(groups)
    if not n or any([r["time_min"] for r in z] != minutes for z in groups.values()):
        raise ContractError(
            "Bounds require every scheduled row, including missing values"
        )
    result = []
    for t in minutes:
        obs = []
        missing = Counter()
        for z in groups.values():
            r = next(r for r in z if r["time_min"] == t)
            if r["status"] == "observed":
                if not lower <= r["vas"] <= upper:
                    raise ContractError("Score outside declared bounds")
                obs.append(r["vas"])
            else:
                code = (
                    r["termination_code"]
                    if r["termination_code"] in ("E", "T")
                    else "other_missing"
                )
                missing[code] += 1
        total = sum(obs)
        m = sum(missing.values())
        result.append(
            dict(
                time_min=t,
                n_candidate=n,
                n_observed=len(obs),
                observed_sum=total,
                n_unobserved_E=missing["E"],
                n_unobserved_T=missing["T"],
                n_other_missing=missing["other_missing"],
                cohort_mean_lower=(total + m * lower) / n,
                cohort_mean_upper=(total + m * upper) / n,
                width_due_to_E=missing["E"] * (upper - lower) / n,
                width_due_to_T=missing["T"] * (upper - lower) / n,
                width_due_to_other_missing=missing["other_missing"]
                * (upper - lower)
                / n,
            )
        )
    return result


def area_bounds(bounds):
    if len(bounds) < 2:
        raise ContractError("Area requires at least two scheduled minutes")
    sums = {
        key: 0.0
        for key in [
            "cohort_mean_lower",
            "cohort_mean_upper",
            "width_due_to_E",
            "width_due_to_T",
            "width_due_to_other_missing",
        ]
    }
    for a, b in zip(bounds, bounds[1:]):
        dt = b["time_min"] - a["time_min"]
        if dt != 1:
            raise ContractError("Area bounds require one-minute scheduled intervals")
        for key in sums:
            sums[key] += (a[key] + b[key]) * dt / 2
    return dict(
        start_min=bounds[0]["time_min"],
        end_min=bounds[-1]["time_min"],
        candidate_mean_auc_lower=sums["cohort_mean_lower"],
        candidate_mean_auc_upper=sums["cohort_mean_upper"],
        width_due_to_E=sums["width_due_to_E"],
        width_due_to_T=sums["width_due_to_T"],
        width_due_to_other_missing=sums["width_due_to_other_missing"],
        unit="VAS_minute",
        interpretation="bounded_grid_trapezoidal_area_not_observed_auc_or_confidence_interval",
    )


def grouped_observed(rows, audit, minutes):
    mapping = {r["subject_id"]: r["eventual_marker"] for r in audit}
    result = []
    for code in ("E", "T", "none"):
        n = sum(v == code for v in mapping.values())
        for t in minutes:
            vals = [
                r["vas"]
                for r in rows
                if mapping[r["subject_id"]] == code
                and r["time_min"] == t
                and r["status"] == "observed"
            ]
            result.append(
                dict(
                    eventual_marker=code,
                    time_min=t,
                    n_group=n,
                    n_observed=len(vals),
                    mean_observed=sum(vals) / len(vals) if vals else None,
                )
            )
    return result
