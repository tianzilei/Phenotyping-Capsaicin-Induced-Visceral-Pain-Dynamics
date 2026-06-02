"""
Kaplan-Meier survival analysis for VAS trajectories.
Analyzes pain onset and relief timing.
"""

from typing import Dict

import numpy as np


def compute_km_curves(
    ts_data: np.ndarray,
    onset_thresh: float = 3.0,
    relief_thresh: float = 1.0,
) -> Dict:
    """
    Compute Kaplan-Meier curves for pain onset and relief.

    Parameters
    ----------
    ts_data : np.ndarray
        2D array of VAS values (subjects x timepoints).
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
        - logrank_pvalue: p-value from log-rank test
    """
    from lifelines import KaplanMeierFitter
    from lifelines.statistics import logrank_test

    n_timepoints = ts_data.shape[1]

    # Event 1: First VAS > onset_thresh
    event1_time, event1_observed = [], []
    for row in ts_data:
        above = np.where(row > onset_thresh)[0]
        if len(above) > 0:
            event1_time.append(above[0])
            event1_observed.append(1)
        else:
            event1_time.append(n_timepoints - 1)
            event1_observed.append(0)

    # Event 2: First VAS < relief_thresh after peak
    event2_time, event2_observed = [], []
    for row in ts_data:
        if np.all(np.isnan(row)):
            event2_time.append(n_timepoints - 1)
            event2_observed.append(0)
            continue
        peak_idx = np.nanargmax(row)
        after_peak = row[peak_idx:]
        below = np.where(after_peak < relief_thresh)[0]
        if len(below) > 0:
            event2_time.append(peak_idx + below[0])
            event2_observed.append(1)
        else:
            event2_time.append(n_timepoints - 1)
            event2_observed.append(0)

    # Fit models
    kmf1 = KaplanMeierFitter()
    kmf2 = KaplanMeierFitter()

    kmf1.fit(
        event1_time,
        event_observed=event1_observed,
        label=f"VAS > {onset_thresh} (Onset)",
    )
    kmf2.fit(
        event2_time,
        event_observed=event2_observed,
        label=f"VAS < {relief_thresh} (Relief)",
    )

    # Log-rank test
    result = logrank_test(
        event1_time,
        event2_time,
        event_observed_A=event1_observed,
        event_observed_B=event2_observed,
    )

    return {
        "kmf_onset": kmf1,
        "kmf_relief": kmf2,
        "onset_time": event1_time,
        "onset_observed": event1_observed,
        "relief_time": event2_time,
        "relief_observed": event2_observed,
        "logrank_pvalue": result.p_value,
    }


def summarize_survival(km_result: Dict) -> str:
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
    pval = km_result["logrank_pvalue"]

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

    lines.append("\n== Log-rank Test ==")
    lines.append(f"p-value: {pval:.4f}")
    sig = "Statistically significant" if pval < 0.05 else "No significant difference"
    lines.append(sig)

    return "\n".join(lines)
