"""
Generate Table S4: Summary of adverse events.
"""

import pandas as pd

from analysis.tables.formatter import df_to_markdown


def generate_adverse_events_table(
    caption: str = "Table S4. Summary of Adverse Events",
) -> str:
    """
    Generate Table S4 (adverse events summary).

    Based on the study protocol: no adverse events were recorded.
    If adverse event data becomes available, this function should accept
    a DataFrame parameter.

    Parameters
    ----------
    caption : str
        Table caption.

    Returns
    -------
    str
        Markdown-formatted table.
    """
    rows = [
        {
            "Safety outcome": "Any adverse event",
            "Number of participants": 0,
            "Percentage": "0.0%",
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
            "Number of participants": 0,
            "Percentage": "0.0%",
        },
        {
            "Safety outcome": "Hospitalization",
            "Number of participants": 0,
            "Percentage": "0.0%",
        },
    ]
    df = pd.DataFrame(rows)
    return df_to_markdown(df, caption=caption)
