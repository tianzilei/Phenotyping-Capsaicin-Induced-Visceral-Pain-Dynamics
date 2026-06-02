"""
Plotting functions for VAS trajectory analysis.
"""

from typing import Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.constants import CLUSTER_COLORS
from analysis.visualization.plots import save_figure


def plot_vas_trajectories(
    df_long: pd.DataFrame,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (10, 6),
) -> plt.Figure:
    """
    Plot mean VAS trajectory with sample size histogram.

    Parameters
    ----------
    df_long : pd.DataFrame
        Long-format VAS data with columns: time_min, vas_value.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    summary = (
        df_long.groupby("time_min")["vas_value"]
        .agg(["mean", "sem", "count"])
        .reset_index()
    )
    summary.rename(columns={"count": "n"}, inplace=True)

    fig, ax1 = plt.subplots(figsize=figsize)

    ax1.errorbar(
        summary["time_min"],
        summary["mean"],
        yerr=summary["sem"],
        fmt="-o",
        capsize=4,
        linewidth=2,
        markersize=5,
        label="Mean VAS ± SE",
    )
    ax1.set_xlabel("Time (minutes)")
    ax1.set_ylabel("VAS Score")
    ax1.set_title("VAS Score Over Time with Sample Size")
    ax1.grid(True)

    ax2 = ax1.twinx()
    ax2.bar(
        summary["time_min"],
        summary["n"],
        color="gray",
        alpha=0.3,
        width=0.8,
        label="Valid Responses (n)",
        zorder=0,
    )
    ax2.set_ylabel("Sample Count", color="gray")
    ax2.tick_params(axis="y", labelcolor="gray")

    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def plot_cluster_centroids(
    centroids: np.ndarray,
    labels: np.ndarray,
    title: str = "DTW-KMeans Cluster Centroids",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (8, 5),
    colors: Optional[list] = None,
    normalize: bool = True,
) -> plt.Figure:
    """
    Plot cluster centroids.

    Parameters
    ----------
    centroids : np.ndarray
        Centroid arrays (n_clusters, n_timepoints).
    labels : np.ndarray
        Cluster labels for counting.
    title : str
        Plot title.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.
    colors : list, optional
        Colors for each cluster.
    normalize : bool
        Whether data was normalized.

    Returns
    -------
    matplotlib.figure.Figure
    """
    if colors is None:
        colors = CLUSTER_COLORS

    centroids_2d = centroids.squeeze()
    n_clusters = centroids_2d.shape[0]
    time = np.arange(centroids_2d.shape[1])

    fig, ax = plt.subplots(figsize=figsize)

    for k in range(n_clusters):
        n_k = np.sum(labels == k)
        ax.plot(
            time,
            centroids_2d[k],
            color=colors[k % len(colors)],
            linewidth=3,
            label=f"Cluster {k + 1} (n={n_k})",
        )

    ax.set_title(title, fontsize=13)
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Normalized Pain Intensity" if normalize else "Pain Intensity")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.25)
    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def plot_silhouette(
    sil_values: np.ndarray,
    labels: np.ndarray,
    sil_avg: float,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (8, 6),
) -> plt.Figure:
    """
    Plot silhouette analysis.

    Parameters
    ----------
    sil_values : np.ndarray
        Per-sample silhouette values.
    labels : np.ndarray
        Cluster labels.
    sil_avg : float
        Average silhouette score.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    n_clusters = len(np.unique(labels))
    y_lower = 10

    fig, ax = plt.subplots(figsize=figsize)

    for k in range(n_clusters):
        kth_vals = sil_values[labels == k]
        kth_vals.sort()

        size_k = len(kth_vals)
        y_upper = y_lower + size_k

        ax.fill_betweenx(
            np.arange(y_lower, y_upper),
            0,
            kth_vals,
            alpha=0.7,
            label=f"Cluster {k} (n={size_k})",
        )

        ax.text(-0.05, y_lower + 0.5 * size_k, str(k))
        y_lower = y_upper + 10

    ax.axvline(x=sil_avg, linestyle="--", linewidth=2, label=f"Average = {sil_avg:.3f}")
    ax.set_title("Silhouette Plot for DTW-KMeans Clustering")
    ax.set_xlabel("Silhouette coefficient")
    ax.set_ylabel("Cluster")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.2)
    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def plot_k_selection(
    k_results: pd.DataFrame,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (6, 4),
) -> plt.Figure:
    """
    Plot silhouette scores across different K values.

    Parameters
    ----------
    k_results : pd.DataFrame
        DataFrame with columns: K, DTW_silhouette.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(k_results["K"], k_results["DTW_silhouette"], marker="o", linewidth=2)
    ax.set_xlabel("Number of clusters (K)")
    ax.set_ylabel("Average DTW silhouette score")
    ax.set_title("DTW Silhouette Across Candidate K Values")
    ax.grid(alpha=0.3)
    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def plot_shapelets(
    shapelet_df: pd.DataFrame,
    n_clusters: int = 3,
    save_path: Optional[str] = None,
    figsize_per_cluster: Tuple[int, int] = (14, 3.2),
    normalize: bool = True,
) -> plt.Figure:
    """
    Plot top shapelets for each cluster.

    Parameters
    ----------
    shapelet_df : pd.DataFrame
        Shapelet results from extract_shapelets().
    n_clusters : int
        Number of clusters.
    save_path : str, optional
        Path to save figure.
    figsize_per_cluster : tuple
        Figure size per cluster row.
    normalize : bool
        Whether data was normalized.

    Returns
    -------
    matplotlib.figure.Figure
    """
    colors = CLUSTER_COLORS

    fig, axes = plt.subplots(
        n_clusters,
        1,
        figsize=(figsize_per_cluster[0], figsize_per_cluster[1] * n_clusters),
        squeeze=False,
    )

    for target_cluster in range(1, n_clusters + 1):
        ax = axes[target_cluster - 1, 0]
        cluster_shapelets = shapelet_df[shapelet_df["target_cluster"] == target_cluster]

        for _, s in cluster_shapelets.iterrows():
            shapelet_vals = [s[f"shapelet_pt{j}"] for j in range(1, s["length"] + 1)]
            x = np.arange(s["length"])
            ax.plot(
                x,
                shapelet_vals,
                color=colors[(target_cluster - 1) % len(colors)],
                linewidth=2.5,
            )
            ax.set_title(
                f"C{target_cluster} | L={int(s['length'])} "
                f"AUC={s['auc']:.3f}, d={s['cohens_d']:.2f}",
                fontsize=10,
            )
            ax.set_xlabel("Local time")
            ax.set_ylabel("Normalized signal" if normalize else "Signal")
            ax.grid(alpha=0.25)

    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig
