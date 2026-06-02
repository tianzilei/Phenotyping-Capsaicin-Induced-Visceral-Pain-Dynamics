"""
Shared utilities for VAS prediction: data loading, feature engineering.
"""

from typing import List, Tuple

import numpy as np
import pandas as pd


def get_time_cols(df: pd.DataFrame) -> List[str]:
    """
    Detect and sort time columns (e.g., '1min', '2min', ..., '20min').

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame.

    Returns
    -------
    list of str
        Sorted list of time column names.
    """
    time_cols = [col for col in df.columns if "min" in col and "Avg" not in col]

    def extract_num(col):
        try:
            return int(col.replace("min", ""))
        except ValueError:
            return 0

    time_cols.sort(key=extract_num)
    return time_cols


def clean_time_series(values: pd.Series) -> pd.Series:
    """
    Clean a VAS time series: once E/T appears, all subsequent points become NaN.

    Parameters
    ----------
    values : pd.Series
        Raw VAS values (may contain strings like 'E', 'T').

    Returns
    -------
    pd.Series
        Cleaned float Series with NaN propagation.
    """
    result = pd.to_numeric(values.copy(), errors="coerce")

    raw_str = values.astype(str)
    for i, val in enumerate(raw_str):
        if val in ("E", "T"):
            result.iloc[i:] = np.nan
            break

    return result


def build_sliding_window_features(
    df: pd.DataFrame,
    time_cols: List[str],
    window: int = 3,
    target_mode: str = "delta",
    include_cluster: bool = False,
    include_avg: bool = False,
) -> Tuple[pd.DataFrame, str]:
    """
    Build supervised dataset from sliding windows of VAS time series.

    Parameters
    ----------
    df : pd.DataFrame
        Raw VAS DataFrame with ID and time columns.
    time_cols : list of str
        Time column names.
    window : int
        Sliding window size.
    target_mode : str
        'delta' for next-minute change, 'value' for next-minute value,
        'direction3' for -1/0/+1, 'direction' for binary up/down.
    include_cluster : bool
        Whether to include cluster as a feature.
    include_avg : bool
        Whether to include average VAS as a feature.

    Returns
    -------
    tuple of (pd.DataFrame, str)
        Supervised DataFrame and target column name.
    """
    records = []

    for _, row in df.iterrows():
        subject_id = row.get("ID", row.name)

        # Get numeric values
        raw_vals = row[time_cols]
        vals = clean_time_series(raw_vals)

        vals_list = vals.values.tolist()

        for i in range(window, len(vals_list) - 1):
            # Features: previous window values
            feature_vals = vals_list[i - window : i]
            if any(np.isnan(v) for v in feature_vals):
                continue

            # Current value
            current = vals_list[i]
            if np.isnan(current):
                continue

            # Target
            next_val = vals_list[i + 1]
            if np.isnan(next_val):
                continue

            record = {
                "subject_id": subject_id,
                "time_idx": i,
            }

            # Add lag features
            for j in range(window):
                record[f"lag_{j + 1}"] = feature_vals[j]

            # Add current value
            record["current_vas"] = current

            # Add derived features
            record["window_mean"] = np.mean(feature_vals)
            record["window_std"] = np.std(feature_vals)
            record["window_max"] = np.max(feature_vals)
            record["window_min"] = np.min(feature_vals)
            record["slope"] = np.polyfit(range(window), feature_vals, 1)[0]

            # Add optional features
            if include_cluster and "cluster" in df.columns:
                record["cluster"] = row["cluster"]
            if include_avg and "Avg" in df.columns:
                record["avg_vas"] = row.get("Avg", 0)

            # Compute target
            if target_mode == "delta":
                record["target"] = next_val - current
                target_col = "target"
            elif target_mode == "value":
                record["target"] = next_val
                target_col = "target"
            elif target_mode == "direction3":
                delta = next_val - current
                if delta > 0.1:
                    record["target"] = 1
                elif delta < -0.1:
                    record["target"] = -1
                else:
                    record["target"] = 0
                target_col = "target"
            elif target_mode == "direction":
                record["target"] = 1 if next_val > current else 0
                target_col = "target"
            else:
                raise ValueError(f"Unknown target_mode: {target_mode}")

            records.append(record)

    return pd.DataFrame(records), target_col


def prepare_modeling_data(data: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare data for modeling: drop NaN subject_ids, fill numeric NaNs.

    Parameters
    ----------
    data : pd.DataFrame
        Supervised dataset.

    Returns
    -------
    pd.DataFrame
        Cleaned DataFrame ready for modeling.
    """
    result = data.copy()

    # Drop rows with NaN subject_id
    if "subject_id" in result.columns:
        result = result.dropna(subset=["subject_id"])

    # Fill numeric NaNs with medians
    numeric_cols = result.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if col != "target":
            result[col] = result[col].fillna(result[col].median())

    return result


def make_feature_cols(data: pd.DataFrame) -> List[str]:
    """
    Generate ordered feature column list from available columns.

    Parameters
    ----------
    data : pd.DataFrame
        Modeling dataset.

    Returns
    -------
    list of str
        Feature column names.
    """
    exclude = {"subject_id", "time_idx", "target", "cluster", "avg_vas"}
    feature_cols = [col for col in data.columns if col not in exclude]
    return sorted(feature_cols)
