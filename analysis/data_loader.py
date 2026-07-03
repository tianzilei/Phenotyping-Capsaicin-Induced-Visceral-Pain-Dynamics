"""
Data loading and cleaning utilities for VAS data, metadata, and signals.
"""

import os
import re
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

ECG_EGG_FEATURE_COLUMNS = [
    "mean_HR",
    "median_HR",
    "min_HR",
    "max_HR",
    "HR_sd",
    "HR_cv",
    "mean_RR",
    "median_RR",
    "min_RR",
    "max_RR",
    "SDNN",
    "RMSSD",
    "pNN50",
    "pNN20",
    "CVSD",
    "total_power",
    "LF_power",
    "HF_power",
    "LF_HF_ratio",
    "log_LF",
    "log_HF",
    "log_total_power",
    "LFnu",
    "HFnu",
    "SD1",
    "SD2",
    "SD1_SD2_ratio",
    "ECG_SQI",
    "ECG_artifact_ratio",
    "ECG_RR_edit_ratio",
    "dominant_freq_cpm",
    "mean_freq_cpm",
    "median_freq_cpm",
    "dominant_power",
    "total_power_egg",
    "log_DP",
    "log_total_power_egg",
    "pct_normogastria",
    "pct_bradygastria",
    "pct_tachygastria",
    "power_ratio",
    "spectral_entropy",
    "spectral_flatness",
    "DF_instability",
    "egg_signal_energy",
    "egg_rms",
    "EGG_SQI",
    "EGG_artifact_ratio",
    "hr_egg_correlation",
    "ecg_egg_cross_corr_max",
    "ecg_egg_lag",
    "ecg_egg_coherence_mean",
    "ecg_egg_energy_ratio",
]

GENERATED_BASELINE_COLUMNS = ECG_EGG_FEATURE_COLUMNS + [
    "cluster",
    "top_rome_disease",
    "rome_match_score",
    "predicted_vas_delta",
    "target_vas_delta",
    "predicted_direction",
    "target_direction",
    "prediction_model",
    "delta_model",
    "direction_model",
]


def load_unified_baseline(filepath: str = None) -> pd.DataFrame:
    """
    Load the unified subject baseline info CSV.

    Parameters
    ----------
    filepath : str, optional
        Path to subject_baseline_info.csv. If None, uses default from constants.

    Returns
    -------
    pd.DataFrame
        Full baseline DataFrame with all columns.
    """
    from analysis.constants import SUBJECT_INFO_FILE

    if filepath is None:
        filepath = SUBJECT_INFO_FILE
    return pd.read_csv(filepath)


def strip_generated_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Drop analysis-generated columns from a baseline dataframe."""
    drop_cols = [col for col in GENERATED_BASELINE_COLUMNS if col in df.columns]
    return df.drop(columns=drop_cols)


def _merge_generated_output(
    df: pd.DataFrame, metric_path: Path, columns: list[str], rename_map: dict | None = None
) -> pd.DataFrame:
    if not metric_path.exists():
        return df

    generated = pd.read_csv(metric_path)
    if rename_map:
        generated = generated.rename(columns=rename_map)

    keep_cols = ["ID"] + [col for col in columns if col in generated.columns]
    if len(keep_cols) == 1:
        return df

    generated = generated[keep_cols].copy()
    overlap = [col for col in keep_cols if col != "ID" and col in df.columns]
    if overlap:
        df = df.drop(columns=overlap)
    return df.merge(generated, on="ID", how="left")


def load_analysis_ready_baseline(filepath: str = None) -> pd.DataFrame:
    """
    Load the raw baseline file and optionally merge analysis-generated outputs.

    This keeps ``BaselineData.csv`` as a source-data table while still letting
    downstream analysis reuse derived cluster labels, Rome mapping, prediction
    summaries, and ECG/EGG features when their standalone output files exist.
    """
    from analysis.constants import METRICS_DIR

    df = load_unified_baseline(filepath)
    metrics_dir = Path(METRICS_DIR)

    df = _merge_generated_output(
        df,
        metrics_dir / "trajectory_clustered.csv",
        ["cluster"],
    )
    df = _merge_generated_output(
        df,
        metrics_dir / "textmining_rome_subject_summary.csv",
        ["top_rome_disease", "rome_match_score"],
    )
    df = _merge_generated_output(
        df,
        metrics_dir / "prediction_subject_level.csv",
        [
            "predicted_vas_delta",
            "target_vas_delta",
            "predicted_direction",
            "target_direction",
            "prediction_model",
            "delta_model",
            "direction_model",
        ],
    )
    if "prediction_model" in df.columns and "delta_model" not in df.columns:
        df = df.rename(columns={"prediction_model": "delta_model"})

    ecg_metric_candidates = [
        metrics_dir / "ecg_egg_features_extracted.csv",
        metrics_dir / "ecg_egg_features.csv",
    ]
    for metric_path in ecg_metric_candidates:
        if metric_path.exists():
            df = _merge_generated_output(df, metric_path, ECG_EGG_FEATURE_COLUMNS)
            break

    return df


def get_vas_columns(df: pd.DataFrame) -> List[str]:
    """
    Get VAS time column names from unified baseline.

    Parameters
    ----------
    df : pd.DataFrame
        Baseline DataFrame.

    Returns
    -------
    list of str
        Sorted list of VAS time column names.
    """
    return [col for col in df.columns if col.startswith("VAS_") and "min" in col]


def get_clinical_columns(df: pd.DataFrame) -> List[str]:
    """
    Get clinical feature column names from baseline.

    Parameters
    ----------
    df : pd.DataFrame
        Baseline DataFrame.

    Returns
    -------
    list of str
        List of clinical column names.
    """
    clinical = [
        "Sex",
        "Age",
        "Height_cm",
        "Weight_kg",
        "BMI",
        "cluster",
    ]
    return [c for c in clinical if c in df.columns]


def get_ecg_egg_columns(df: pd.DataFrame) -> List[str]:
    """
    Get ECG/EGG feature column names from baseline.

    Parameters
    ----------
    df : pd.DataFrame
        Baseline DataFrame.

    Returns
    -------
    list of str
        List of ECG/EGG feature column names.
    """
    ecg_egg = [
        "mean_HR",
        "median_HR",
        "min_HR",
        "max_HR",
        "HR_sd",
        "HR_cv",
        "mean_RR",
        "median_RR",
        "min_RR",
        "max_RR",
        "SDNN",
        "RMSSD",
        "pNN50",
        "pNN20",
        "CVSD",
        "total_power",
        "LF_power",
        "HF_power",
        "LF_HF_ratio",
        "log_LF",
        "log_HF",
        "log_total_power",
        "LFnu",
        "HFnu",
        "SD1",
        "SD2",
        "SD1_SD2_ratio",
        "ECG_SQI",
        "ECG_artifact_ratio",
        "ECG_RR_edit_ratio",
        "dominant_freq_cpm",
        "mean_freq_cpm",
        "median_freq_cpm",
        "dominant_power",
        "total_power_egg",
        "log_DP",
        "log_total_power_egg",
        "pct_normogastria",
        "pct_bradygastria",
        "pct_tachygastria",
        "power_ratio",
        "spectral_entropy",
        "spectral_flatness",
        "DF_instability",
        "egg_signal_energy",
        "egg_rms",
        "EGG_SQI",
        "EGG_artifact_ratio",
        "hr_egg_correlation",
        "ecg_egg_cross_corr_max",
        "ecg_egg_lag",
        "ecg_egg_coherence_mean",
        "ecg_egg_energy_ratio",
    ]
    return [c for c in ecg_egg if c in df.columns]


def get_symptom_columns(df: pd.DataFrame) -> List[str]:
    """
    Get symptom column names from baseline.

    Parameters
    ----------
    df : pd.DataFrame
        Baseline DataFrame.

    Returns
    -------
    list of str
        List of symptom column names.
    """
    symptoms = ["Region_code", "Symptom_codes", "Additional_symptoms"]
    return [c for c in symptoms if c in df.columns]


def load_vas_from_unified(df: pd.DataFrame) -> pd.DataFrame:
    """
    Load VAS data from unified baseline DataFrame and convert to long format.

    Parameters
    ----------
    df : pd.DataFrame
        Unified baseline DataFrame with VAS_1min, VAS_2min, ..., VAS_20min columns.

    Returns
    -------
    pd.DataFrame
        Long-format DataFrame with columns: ID, time, vas_value, time_min.
    """
    time_cols = get_vas_columns(df)

    if not time_cols:
        raise ValueError("No VAS columns found in DataFrame")

    df_long = df.melt(
        id_vars="ID", value_vars=time_cols, var_name="time", value_name="vas_value"
    )

    df_long = df_long[~df_long["vas_value"].isin(["E", "T"])]
    df_long["vas_value"] = pd.to_numeric(df_long["vas_value"], errors="coerce")
    df_long.dropna(subset=["vas_value"], inplace=True)

    df_long["time_min"] = df_long["time"].str.extract(r"(\d+)").astype(int)

    return df_long


def load_vas_wide_from_unified(df: pd.DataFrame) -> pd.DataFrame:
    """
    Load VAS data from unified baseline and return wide-format DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Unified baseline DataFrame.

    Returns
    -------
    pd.DataFrame
        Wide-format DataFrame with subjects as rows and time columns.
    """
    time_cols = get_vas_columns(df)

    if not time_cols:
        raise ValueError("No VAS columns found in DataFrame")

    df_long = df.melt(
        id_vars="ID", value_vars=time_cols, var_name="time", value_name="vas_value"
    )

    df_long = df_long[~df_long["vas_value"].isin(["E", "T"])]
    df_long["vas_value"] = pd.to_numeric(df_long["vas_value"], errors="coerce")
    df_long["time_min"] = df_long["time"].str.extract(r"(\d+)").astype(int)

    df_wide = df_long.pivot(index="ID", columns="time_min", values="vas_value")

    return df_wide


def load_vas_data(filepath: str) -> pd.DataFrame:
    """
    Load VAS data from CSV and convert to long format.
    Supports both legacy format (1min, 2min...) and unified format
    (VAS_1min, VAS_2min...).

    Parameters
    ----------
    filepath : str
        Path to CSV file.

    Returns
    -------
    pd.DataFrame
        Long-format DataFrame with columns: ID, time, vas_value, time_min.
    """
    df = pd.read_csv(filepath)

    time_cols = get_time_cols(df)

    if not time_cols:
        time_cols = get_vas_columns(df)
        if time_cols:
            time_cols = get_vas_columns(df)

    df_long = df.melt(
        id_vars="ID", value_vars=time_cols, var_name="time", value_name="vas_value"
    )

    df_long = df_long[~df_long["vas_value"].isin(["E", "T"])]
    df_long["vas_value"] = pd.to_numeric(df_long["vas_value"], errors="coerce")
    df_long.dropna(subset=["vas_value"], inplace=True)

    df_long["time_min"] = df_long["time"].str.extract(r"(\d+)").astype(int)

    return df_long


def load_vas_wide(filepath: str) -> pd.DataFrame:
    """
    Load VAS data and return wide-format DataFrame (subjects x time).

    Parameters
    ----------
    filepath : str
        Path to CSV file.

    Returns
    -------
    pd.DataFrame
        Wide-format DataFrame with subjects as rows and time columns.
    """
    df = pd.read_csv(filepath)
    time_cols = get_time_cols(df)

    if not time_cols:
        time_cols = get_vas_columns(df)

    df_long = df.melt(
        id_vars="ID", value_vars=time_cols, var_name="time", value_name="vas_value"
    )

    df_long = df_long[~df_long["vas_value"].isin(["E", "T"])]
    df_long["vas_value"] = pd.to_numeric(df_long["vas_value"], errors="coerce")
    df_long["time_min"] = df_long["time"].str.extract(r"(\d+)").astype(int)

    df_wide = df_long.pivot(index="ID", columns="time_min", values="vas_value")

    return df_wide


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
        match = re.search(r"(\d+)\s*min", str(col))
        return int(match.group(1)) if match else 0

    time_cols.sort(key=extract_num)
    return time_cols


def clean_vas_time_series(values: pd.Series) -> pd.Series:
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
    result = values.copy()

    # Convert to numeric
    result = pd.to_numeric(result, errors="coerce")

    # Find first E/T marker and set everything after to NaN
    raw_str = values.astype(str)
    for i, val in enumerate(raw_str):
        if val in ("E", "T"):
            result.iloc[i:] = np.nan
            break

    return result


def load_subject_metadata(filepath: str) -> pd.DataFrame:
    """
    Load subject baseline metadata CSV.

    Parameters
    ----------
    filepath : str
        Path to subject_baseline_info.csv.

    Returns
    -------
    pd.DataFrame
        Metadata DataFrame with file_stem column added.
    """
    subject_info = pd.read_csv(filepath)

    # Create file_stem from ACQ_CNP_files
    if "ACQ_CNP_files" in subject_info.columns:
        subject_info["file_stem"] = subject_info["ACQ_CNP_files"].str.replace(
            ".acq", "", regex=False
        )

    return subject_info


def load_signal(filepath: str) -> np.ndarray:
    """
    Load a signal CSV file as a numpy array.

    Parameters
    ----------
    filepath : str
        Path to CSV signal file.

    Returns
    -------
    np.ndarray
        Signal data as float64 array.
    """
    return pd.read_csv(filepath).values.astype(np.float64)


def check_signal_files(
    meta: pd.DataFrame, data_dir: str, ecg_suffix: str = "", egg_suffix: str = "_egg"
) -> pd.DataFrame:
    """
    Filter metadata to only subjects with existing signal files.

    Parameters
    ----------
    meta : pd.DataFrame
        Metadata DataFrame with 'file_stem' column.
    data_dir : str
        Directory containing signal files.
    ecg_suffix : str
        Suffix added before .csv for ECG files.
    egg_suffix : str
        Suffix added before .csv for EGG files.

    Returns
    -------
    pd.DataFrame
        Filtered metadata with only valid subjects.
    """
    valid = []
    for _, row in meta.iterrows():
        stem = row.get("file_stem", "")
        if not stem:
            continue
        ecg_path = os.path.join(data_dir, f"{stem}{ecg_suffix}.csv")
        egg_path = os.path.join(data_dir, f"{stem}{egg_suffix}.csv")
        if os.path.exists(ecg_path) and os.path.exists(egg_path):
            valid.append(row)
    return pd.DataFrame(valid)
