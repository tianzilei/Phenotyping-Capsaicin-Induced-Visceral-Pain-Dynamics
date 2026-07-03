"""
Markdown table formatting utilities.
"""

from typing import Optional

import pandas as pd


def df_to_markdown(
    df: pd.DataFrame,
    caption: Optional[str] = None,
    float_fmt: str = ".3f",
    index: bool = False,
) -> str:
    """
    Convert a DataFrame to a Markdown table string.

    Parameters
    ----------
    df : pd.DataFrame
        Table data.
    caption : str, optional
        Table caption (printed above the table).
    float_fmt : str
        Format string for float columns.
    index : bool
        Whether to include the index column.

    Returns
    -------
    str
        Markdown-formatted table.
    """
    lines = []
    if caption:
        lines.append(f"**{caption}**")
        lines.append("")

    # Format floats
    df_fmt = df.copy()
    for col in df_fmt.columns:
        if pd.api.types.is_float_dtype(df_fmt[col]):
            df_fmt[col] = df_fmt[col].apply(
                lambda x: f"{x:{float_fmt}}" if pd.notna(x) else ""
            )

    if index:
        df_fmt = df_fmt.reset_index()
    md = _simple_markdown_table(df_fmt)
    lines.append(md)
    lines.append("")
    return "\n".join(lines)


def _simple_markdown_table(df: pd.DataFrame) -> str:
    """Render a GitHub-flavored Markdown table without optional dependencies."""
    columns = [str(col) for col in df.columns]
    rows = [
        [str(value) if pd.notna(value) else "" for value in row]
        for row in df.to_numpy()
    ]
    widths = []
    for idx, col in enumerate(columns):
        cell_widths = [len(row[idx]) for row in rows] if rows else [0]
        widths.append(max(len(col), *cell_widths))

    def fmt_row(values: list[str]) -> str:
        cells = [f" {value:<{widths[idx]}} " for idx, value in enumerate(values)]
        return "|" + "|".join(cells) + "|"

    header = fmt_row(columns)
    separator = "|" + "|".join(f" {'-' * width} " for width in widths) + "|"
    body = [fmt_row(row) for row in rows]
    return "\n".join([header, separator, *body])


def build_table_1_row(
    characteristic: str,
    value: str,
    subcategory: bool = False,
) -> dict:
    """Build a single row for Table 1 (baseline characteristics)."""
    prefix = "    " if subcategory else ""
    return {
        "Characteristic": f"{prefix}{characteristic}",
        "Value": value,
    }


def format_mean_sd(values) -> str:
    """Format as mean ± SD."""
    mean = values.mean()
    std = values.std()
    return f"{mean:.1f} ± {std:.1f}"


def format_median_iqr(values) -> str:
    """Format as median (IQR)."""
    median = values.median()
    q25 = values.quantile(0.25)
    q75 = values.quantile(0.75)
    return f"{median:.1f} ({q25:.1f}–{q75:.1f})"


def format_n_percent(n: int, total: int) -> str:
    """Format as n (%)."""
    pct = n / total * 100
    return f"{n} ({pct:.1f}%)"
