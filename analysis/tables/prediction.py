"""
Generate Table S3: Short-term direction prediction model performance.
"""

import pandas as pd

from analysis.tables.formatter import df_to_markdown


def generate_prediction_table(
    fold_metrics_df: pd.DataFrame,
    caption: str = "Table S3. Performance of Short-Term Direction Prediction Models",
) -> str:
    """
    Generate Table S3 from classification fold metrics.

    Parameters
    ----------
    fold_metrics_df : pd.DataFrame
        DataFrame with model, accuracy, balanced accuracy, F1, and fold columns.
    caption : str
        Table caption.

    Returns
    -------
    str
        Markdown-formatted table.
    """
    # Compute mean ± SD across folds for each model
    summary = []
    for model_name, group in fold_metrics_df.groupby("model"):
        accuracy = f"{group['accuracy'].mean():.3f} ± {group['accuracy'].std():.3f}"
        balanced = (
            f"{group['balanced_accuracy'].mean():.3f} ± "
            f"{group['balanced_accuracy'].std():.3f}"
        )
        macro = f"{group['f1_macro'].mean():.3f} ± {group['f1_macro'].std():.3f}"
        weighted = (
            f"{group['f1_weighted'].mean():.3f} ± {group['f1_weighted'].std():.3f}"
        )
        summary.append(
            {
                "Model": model_name,
                "Accuracy (mean ± SD)": accuracy,
                "Balanced Accuracy": balanced,
                "Macro F1": macro,
                "Weighted F1": weighted,
            }
        )

    summary_df = pd.DataFrame(summary)
    # Reorder rows to match manuscript order
    order = ["Majority", "PersistenceDir", "Logistic"]
    summary_df["_sort"] = summary_df["Model"].apply(
        lambda x: order.index(x) if x in order else 99
    )
    summary_df = (
        summary_df.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
    )

    return df_to_markdown(summary_df, caption=caption)
