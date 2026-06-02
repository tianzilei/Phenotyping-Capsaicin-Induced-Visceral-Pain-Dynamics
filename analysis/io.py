"""
I/O utilities for saving metrics tables, predictions, and CSV files.
"""

import os

import pandas as pd


def save_csv(
    df: pd.DataFrame, path: str, index: bool = False, encoding: str = "utf-8-sig"
) -> str:
    """
    Save DataFrame to CSV with standardized encoding.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to save.
    path : str
        Output file path.
    index : bool
        Whether to write row indices.
    encoding : str
        File encoding.

    Returns
    -------
    str
        Path to saved file.
    """
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    df.to_csv(path, index=index, encoding=encoding)
    return path


def save_metrics_tables(
    fold_metrics_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    outdir: str,
    prefix: str = "",
) -> tuple:
    """
    Save fold-level and summary metrics to CSV files.

    Parameters
    ----------
    fold_metrics_df : pd.DataFrame
        Per-fold metrics.
    summary_df : pd.DataFrame
        Aggregated summary metrics.
    outdir : str
        Output directory.
    prefix : str
        Optional filename prefix.

    Returns
    -------
    tuple of (str, str)
        Paths to fold_metrics.csv and summary_metrics.csv.
    """
    os.makedirs(outdir, exist_ok=True)

    fold_path = os.path.join(
        outdir, f"{prefix}fold_metrics.csv" if prefix else "fold_metrics.csv"
    )
    summary_path = os.path.join(
        outdir, f"{prefix}summary_metrics.csv" if prefix else "summary_metrics.csv"
    )

    fold_metrics_df.to_csv(fold_path, index=False)
    summary_df.to_csv(summary_path, index=False)

    return fold_path, summary_path


def save_prediction_table(
    pred_df: pd.DataFrame,
    outdir: str,
    filename: str = "all_predictions.csv",
) -> str:
    """
    Save all predictions to CSV.

    Parameters
    ----------
    pred_df : pd.DataFrame
        Predictions DataFrame.
    outdir : str
        Output directory.
    filename : str
        Output filename.

    Returns
    -------
    str
        Path to saved file.
    """
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, filename)
    pred_df.to_csv(path, index=False)
    return path


def save_model_summary(
    text: str, outdir: str, filename: str = "model_summary.txt"
) -> str:
    """
    Save text summary to file.

    Parameters
    ----------
    text : str
        Summary text.
    outdir : str
        Output directory.
    filename : str
        Output filename.

    Returns
    -------
    str
        Path to saved file.
    """
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
