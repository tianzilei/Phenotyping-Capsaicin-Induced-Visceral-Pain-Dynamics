"""
Change point detection for VAS trajectories.
Includes threshold-based, derivative-based, and PELT methods.
"""

import numpy as np
import pandas as pd


def detect_pain_onset(row: pd.Series, threshold: float = 3.0) -> float:
    """
    Detect pain onset using threshold method.

    Parameters
    ----------
    row : pd.Series
        VAS time series for one subject (time columns as index).
    threshold : float
        VAS threshold for pain onset.

    Returns
    -------
    float
        Time index of first VAS >= threshold, or np.nan.
    """
    above = row >= threshold
    if above.any():
        return row.index[above.argmax()]
    return np.nan


def detect_derivative_onset(row: pd.Series, delta_thresh: float = 0.5) -> float:
    """
    Detect pain onset using derivative method.

    Parameters
    ----------
    row : pd.Series
        VAS time series for one subject.
    delta_thresh : float
        Minimum change in VAS for onset detection.

    Returns
    -------
    float
        Time index of first delta >= delta_thresh, or np.nan.
    """
    diffs = row.diff()
    above = diffs >= delta_thresh
    if above.any():
        return row.index[above.argmax()]
    return np.nan


def detect_rank_change_point(row: pd.Series, penalty: float = 0.5) -> float:
    """
    Detect change point using ruptures PELT with rank model.

    Parameters
    ----------
    row : pd.Series
        VAS time series for one subject.
    penalty : float
        Penalty parameter for PELT algorithm.

    Returns
    -------
    float
        Detected change point index, or np.nan on failure.
    """
    try:
        import ruptures as rpt

        signal = row.values.astype(float)
        algo = rpt.Pelt(model="rank").fit(signal)
        result = algo.predict(pen=penalty)
        return result[0] if result else np.nan
    except Exception:
        return np.nan


def detect_all_onsets(
    df_wide: pd.DataFrame,
    threshold: float = 3.0,
    delta_thresh: float = 0.5,
    penalty: float = 0.5,
) -> pd.DataFrame:
    """
    Run all onset/change point detection methods on wide-format VAS data.

    Parameters
    ----------
    df_wide : pd.DataFrame
        Wide-format VAS DataFrame (subjects x time).
    threshold : float
        Threshold for pain onset detection.
    delta_thresh : float
        Delta threshold for derivative onset.
    penalty : float
        PELT penalty parameter.

    Returns
    -------
    pd.DataFrame
        DataFrame with ID, onset, derivative onset, and rank change point.
    """
    results = []

    for idx, row in df_wide.iterrows():
        onset_thresh = detect_pain_onset(row, threshold=threshold)
        onset_deriv = detect_derivative_onset(row, delta_thresh=delta_thresh)
        cp_rank = detect_rank_change_point(row, penalty=penalty)

        results.append(
            {
                "ID": idx,
                "pain_onset_min": onset_thresh,
                "pain_onset_derivative": onset_deriv,
                "change_point_rank": cp_rank,
            }
        )

    return pd.DataFrame(results)
