"""
Plotting functions for prediction results.
"""

from typing import Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.constants import CONFUSION_CMAP, PRIMARY_COLOR
from analysis.visualization.plots import save_figure


def plot_observed_vs_predicted(
    pred_df: pd.DataFrame,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (6, 6),
) -> plt.Figure:
    """
    Plot observed vs predicted scatter plot.

    Parameters
    ----------
    pred_df : pd.DataFrame
        Predictions DataFrame with 'target' and 'predicted' columns.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)

    ax.scatter(
        pred_df["target"],
        pred_df["predicted"],
        alpha=0.3,
        edgecolors="w",
        linewidth=0.5,
    )

    lims = [
        min(pred_df["target"].min(), pred_df["predicted"].min()),
        max(pred_df["target"].max(), pred_df["predicted"].max()),
    ]
    ax.plot(lims, lims, "--", color="gray", alpha=0.8, label="Identity")
    ax.set_xlim(lims)
    ax.set_ylim(lims)

    ax.set_xlabel("Observed")
    ax.set_ylabel("Predicted")
    ax.set_title("Observed vs Predicted")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def plot_mean_curve(
    pred_df: pd.DataFrame,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (8, 5),
) -> plt.Figure:
    """
    Plot mean observed vs predicted curves by time index.

    Parameters
    ----------
    pred_df : pd.DataFrame
        Predictions DataFrame with 'time_idx', 'target', 'predicted' columns.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    mean_by_time = pred_df.groupby("time_idx")[["target", "predicted"]].mean()

    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(
        mean_by_time.index, mean_by_time["target"], "o-", label="Observed", linewidth=2
    )
    ax.plot(
        mean_by_time.index,
        mean_by_time["predicted"],
        "s--",
        label="Predicted",
        linewidth=2,
    )

    ax.set_xlabel("Time Index")
    ax.set_ylabel("VAS")
    ax.set_title("Mean Observed vs Predicted by Time")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def plot_confusion_matrix(
    cm: np.ndarray,
    labels: list,
    title: str = "Confusion Matrix",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (6, 5),
) -> plt.Figure:
    """
    Plot confusion matrix heatmap.

    Parameters
    ----------
    cm : np.ndarray
        Confusion matrix.
    labels : list
        Class labels.
    title : str
        Plot title.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(cm, interpolation="nearest", cmap=CONFUSION_CMAP)
    ax.set_title(title)
    plt.colorbar(im, ax=ax)

    tick_marks = np.arange(len(labels))
    ax.set_xticks(tick_marks)
    ax.set_xticklabels(labels, rotation=45)
    ax.set_yticks(tick_marks)
    ax.set_yticklabels(labels)

    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")

    # Add text annotations
    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(
                j,
                i,
                str(cm[i, j]),
                ha="center",
                va="center",
                color="white" if cm[i, j] > thresh else "black",
                fontsize=14,
            )

    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def plot_metric_bars(
    summary_df: pd.DataFrame,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (10, 4),
) -> plt.Figure:
    """
    Plot bar charts for each metric.

    Parameters
    ----------
    summary_df : pd.DataFrame
        Summary metrics DataFrame.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    metrics = summary_df.columns.tolist()
    n_metrics = len(metrics)

    fig, axes = plt.subplots(1, n_metrics, figsize=figsize)
    if n_metrics == 1:
        axes = [axes]

    for ax, metric in zip(axes, metrics):
        value = summary_df[metric].values[0]
        ax.bar([metric], [value], color=PRIMARY_COLOR)
        ax.set_ylim(0, 1)
        ax.set_title(metric)
        ax.set_ylabel("Score")

    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def plot_time_stratified_performance(
    pred_df: pd.DataFrame,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (10, 5),
) -> plt.Figure:
    """
    Plot performance metrics stratified by time index.

    Parameters
    ----------
    pred_df : pd.DataFrame
        Predictions DataFrame with 'time_idx', 'target', 'predicted' columns.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    from analysis.prediction.classification import compute_classification_metrics

    time_groups = pred_df.groupby("time_idx")
    time_metrics = []

    for time_idx, group in time_groups:
        if len(group["target"].unique()) < 2:
            continue
        metrics = compute_classification_metrics(
            group["target"].values, group["predicted"].values
        )
        metrics["time_idx"] = time_idx
        time_metrics.append(metrics)

    if not time_metrics:
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "No valid time points", ha="center", va="center")
        return fig

    metrics_df = pd.DataFrame(time_metrics)

    fig, axes = plt.subplots(1, 3, figsize=figsize)

    for ax, metric in zip(axes, ["accuracy", "balanced_accuracy", "f1_macro"]):
        ax.plot(metrics_df["time_idx"], metrics_df[metric], "o-", linewidth=2)
        ax.set_xlabel("Time Index")
        ax.set_ylabel(metric.replace("_", " ").title())
        ax.set_title(metric.replace("_", " ").title())
        ax.grid(alpha=0.3)
        ax.set_ylim(0, 1)

    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig
