"""
Generate Table S4: Summary of adverse events.
"""

import pandas as pd

from analysis.data_loader import get_vas_columns
from analysis.tables.formatter import df_to_markdown


def generate_adverse_events_table(
    baseline_df: pd.DataFrame,
    caption: str = "Table S4. Summary of Adverse Events",
) -> str:
    """
    Generate Table S4 (adverse events summary).

    A T marker in the minute-level VAS series denotes trial termination and is
    counted as an adverse event. E denotes early completion and is not counted
    as an adverse event.

    Parameters
    ----------
    baseline_df : pd.DataFrame
        Raw baseline DataFrame containing minute-level VAS columns.
    caption : str
        Table caption.

    Returns
    -------
    str
        Markdown-formatted table.
    """
    vas_cols = get_vas_columns(baseline_df)
    t_mask = baseline_df[vas_cols].apply(
        lambda row: row.astype(str).str.strip().eq("T").any(), axis=1
    )
    total_n = len(baseline_df)
    any_ae_n = int(t_mask.sum())
    any_ae_pct = f"{(any_ae_n / total_n) * 100:.1f}%"

    rows = [
        {
            "Safety outcome": "Any adverse event",
            "Number of participants": any_ae_n,
            "Percentage": any_ae_pct,
        },
        {
            "Safety outcome": "Serious adverse event",
            "Number of participants": 0,
            "Percentage": "0.0%",
        },
        {
            "Safety outcome": "Medical intervention required",
            "Number of participants": 0,
            "Percentage": "0.0%",
        },
        {
            "Safety outcome": "Protocol discontinuation due to adverse event",
            "Number of participants": any_ae_n,
            "Percentage": any_ae_pct,
        },
        {
            "Safety outcome": "Hospitalization",
            "Number of participants": 0,
            "Percentage": "0.0%",
        },
    ]
    df = pd.DataFrame(rows)
    return df_to_markdown(df, caption=caption)
