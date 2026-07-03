"""
Kaplan-Meier survival analysis for VAS trajectories.
Analyzes pain onset and relief timing.
"""

from __future__ import annotations

import numpy as np


def compute_km_curves(
    ts_data: np.ndarray,
    time_values: np.ndarray | None = None,
    onset_thresh: float = 3.0,
    relief_thresh: float = 1.0,
) -> dict:
    """
    Compute Kaplan-Meier curves for pain onset and relief.

    Parameters
    ----------
    ts_data : np.ndarray
        2D array of VAS values (subjects x timepoints).
    time_values : np.ndarray, optional
        Observed time labels corresponding to columns in ``ts_data``.
    onset_thresh : float
        VAS threshold for pain onset event.
    relief_thresh : float
        VAS threshold for pain relief event (post-peak).

    Returns
    -------
    dict
        Dictionary containing:
        - kmf_onset: fitted KaplanMeierFitter for onset
        - kmf_relief: fitted KaplanMeierFitter for relief
        - onset_time: list of event times
        - onset_observed: list of event indicators
        - relief_time: list of event times
        - relief_observed: list of event indicators
        - comparison_note: explanation of why no direct log-rank comparison is used
    """
    from lifelines import KaplanMeierFitter

    n_timepoints = ts_data.shape[1]
    if time_values is None:
        time_values = np.arange(1, n_timepoints + 1)
    else:
        time_values = np.asarray(time_values)
        if len(time_values) != n_timepoints:
            raise ValueError("time_values must have the same length as ts_data columns")

    # Event 1: First VAS >= onset_thresh
    event1_time, event1_observed = [], []
    for row in ts_data:
        valid_mask = ~np.isnan(row)
        if not np.any(valid_mask):
            event1_time.append(time_values[0])
            event1_observed.append(0)
            continue
        observed_times = time_values[valid_mask]
        observed_values = row[valid_mask]
        above = np.where(observed_values >= onset_thresh)[0]
        if len(above) > 0:
            event1_time.append(observed_times[above[0]])
            event1_observed.append(1)
        else:
            event1_time.append(observed_times[-1])
            event1_observed.append(0)

    # Event 2: First VAS < relief_thresh after peak
    event2_time, event2_observed = [], []
    for row in ts_data:
        valid_mask = ~np.isnan(row)
        if not np.any(valid_mask):
            event2_time.append(time_values[0])
            event2_observed.append(0)
            continue
        observed_times = time_values[valid_mask]
        observed_values = row[valid_mask]
        peak_idx = int(np.argmax(observed_values))
        after_peak_values = observed_values[peak_idx:]
        after_peak_times = observed_times[peak_idx:]
        below = np.where(after_peak_values < relief_thresh)[0]
        if len(below) > 0:
            event2_time.append(after_peak_times[below[0]])
            event2_observed.append(1)
        else:
            event2_time.append(observed_times[-1])
            event2_observed.append(0)

    # Fit models
    kmf1 = KaplanMeierFitter()
    kmf2 = KaplanMeierFitter()

    kmf1.fit(
        event1_time,
        event_observed=event1_observed,
        label=f"VAS >= {onset_thresh} (Onset)",
    )
    kmf2.fit(
        event2_time,
        event_observed=event2_observed,
        label=f"VAS < {relief_thresh} (Relief)",
    )

    return {
        "kmf_onset": kmf1,
        "kmf_relief": kmf2,
        "onset_time": event1_time,
        "onset_observed": event1_observed,
        "relief_time": event2_time,
        "relief_observed": event2_observed,
        "comparison_note": (
            "No direct log-rank p-value is reported because onset and relief "
            "are different event definitions measured on the same participants."
        ),
    }


def summarize_survival(km_result: dict) -> str:
    """
    Print summary of survival analysis results.

    Parameters
    ----------
    km_result : dict
        Output from compute_km_curves().

    Returns
    -------
    str
        Summary text.
    """
    kmf1 = km_result["kmf_onset"]
    kmf2 = km_result["kmf_relief"]
    lines = ["== Median Time Estimates =="]

    # Onset
    if np.isfinite(kmf1.median_survival_time_):
        lines.append(f"VAS Onset: {kmf1.median_survival_time_}")
    else:
        lines.append("VAS Onset: Median time not reached (right-censored)")

    # Relief
    if np.isfinite(kmf2.median_survival_time_):
        lines.append(f"VAS Relief: {kmf2.median_survival_time_}")
    else:
        lines.append("VAS Relief: Median time not reached (right-censored)")

    lines.append("\n== Comparison Note ==")
    lines.append(km_result["comparison_note"])

    return "\n".join(lines)
