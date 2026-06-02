"""
Generate Table 1: Baseline Characteristics.
"""

from typing import List

import pandas as pd

from analysis.tables.formatter import (
    build_table_1_row,
    df_to_markdown,
    format_mean_sd,
    format_n_percent,
)


def generate_baseline_table(
    df: pd.DataFrame,
    caption: str = "Table 1. Baseline Characteristics of Study Participants",
) -> str:
    """
    Generate Table 1 (baseline characteristics) as Markdown.

    Parameters
    ----------
    df : pd.DataFrame
        Unified baseline DataFrame.
    caption : str
        Table caption.

    Returns
    -------
    str
        Markdown-formatted table.
    """
    total = len(df)
    rows: List[dict] = []

    # Demographics
    rows.append(build_table_1_row("Age, years, mean ± SD", format_mean_sd(df["Age"])))

    # Sex
    sex_map = {"女": "Female", "男": "Male"}
    rows.append(build_table_1_row("Sex, n (%)", ""))
    for sex, count in df["Sex"].value_counts().items():
        label = sex_map.get(str(sex), str(sex))
        rows.append(
            build_table_1_row(label, format_n_percent(count, total), subcategory=True)
        )

    # Anthropometrics
    rows.append(
        build_table_1_row("Height, cm, mean ± SD", format_mean_sd(df["Height_cm"]))
    )
    rows.append(
        build_table_1_row("Weight, kg, mean ± SD", format_mean_sd(df["Weight_kg"]))
    )
    rows.append(build_table_1_row("BMI, kg/m², mean ± SD", format_mean_sd(df["BMI"])))

    # Time since last meal
    if (
        "Time_since_last_meal_h" in df.columns
        and df["Time_since_last_meal_h"].notna().any()
    ):
        rows.append(
            build_table_1_row(
                "Time since last meal, hours, mean ± SD",
                format_mean_sd(df["Time_since_last_meal_h"]),
            )
        )

    # Questionnaire data (if available)
    alcohol_map = {
        "非饮酒者": "Non-drinker",
        "偶尔饮酒者": "Occasional drinker",
        "经常饮酒者": "Regular drinker",
    }
    q_fields = [
        ("Alcohol_consumption", "Alcohol consumption, n (%)"),
        ("Spicy_food_frequency", "Spicy food frequency, mean ± SD"),
        ("Usual_spiciness_level", "Usual spiciness level, mean ± SD"),
        ("Spicy_food_preference", "Preference for spicy food, mean ± SD"),
        ("Max_tolerable_spiciness", "Maximum tolerable spiciness, mean ± SD"),
        ("CCEI", "CCEI, mean ± SD"),
        ("Recent_spicy_intake_24h", "Recent spicy food intake (24h), n (%)"),
        ("Time_since_last_intake_h", "Time since last intake, hours, mean ± SD"),
        ("Spicy_episodes_24h", "Number of episodes (24h), mean ± SD"),
        ("AES", "AES, mean ± SD"),
        ("Baseline_GI_symptoms", "Baseline GI symptoms, n (%)"),
    ]

    for col, label in q_fields:
        if col not in df.columns:
            continue
        if df[col].notna().sum() == 0:
            continue

        if pd.api.types.is_numeric_dtype(df[col]):
            rows.append(build_table_1_row(label, format_mean_sd(df[col].dropna())))
        else:
            rows.append(build_table_1_row(label, ""))
            for val, count in df[col].value_counts().items():
                if col == "Alcohol_consumption":
                    val_label = alcohol_map.get(str(val), str(val))
                else:
                    val_label = str(val)
                rows.append(
                    build_table_1_row(
                        val_label, format_n_percent(count, total), subcategory=True
                    )
                )

    # Cluster (if available)
    if "cluster" in df.columns and df["cluster"].notna().any():
        rows.append(build_table_1_row("Cluster assignment, n (%)", ""))
        for cl, count in df["cluster"].value_counts().sort_index().items():
            rows.append(
                build_table_1_row(
                    f"Cluster {int(cl) + 1}",
                    format_n_percent(count, total),
                    subcategory=True,
                )
            )

    table_df = pd.DataFrame(rows)
    return df_to_markdown(table_df, caption=caption)
