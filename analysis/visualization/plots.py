"""
Generic plotting functions for bar charts, line plots, scatter plots, and heatmaps.
"""

import os
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np

from analysis.constants import HEATMAP_CMAP, PRIMARY_COLOR


def save_figure(fig: plt.Figure, path: str, dpi: int = 150, **kwargs) -> str:
    """
    Save matplotlib figure to file.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        Figure to save.
    path : str
        Output file path.
    dpi : int
        Resolution.

    Returns
    -------
    str
        Path to saved file.
    """
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight", **kwargs)
    plt.close(fig)
    return path


def bar_chart(
    x: list,
    y: list,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (8, 5),
    color: str = PRIMARY_COLOR,
    horizontal: bool = False,
) -> plt.Figure:
    """
    Create a bar chart.

    Parameters
    ----------
    x : list
        Categories or values.
    y : list
        Values or categories.
    title : str
        Plot title.
    xlabel : str
        X-axis label.
    ylabel : str
        Y-axis label.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.
    color : str
        Bar color.
    horizontal : bool
        If True, create horizontal bar chart.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)

    if horizontal:
        ax.barh(x, y, color=color)
        ax.set_xlabel(ylabel)
        ax.set_ylabel(xlabel)
    else:
        ax.bar(x, y, color=color)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

    ax.set_title(title)
    plt.xticks(rotation=45 if not horizontal else 0, ha="right")
    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def line_plot(
    x: list,
    y_lists: list,
    labels: Optional[list] = None,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (8, 5),
    colors: Optional[list] = None,
    linewidth: float = 2.0,
    grid: bool = True,
) -> plt.Figure:
    """
    Create a line plot with multiple series.

    Parameters
    ----------
    x : list
        X values.
    y_lists : list of list
        Y values for each series.
    labels : list of str, optional
        Legend labels.
    title : str
        Plot title.
    xlabel, ylabel : str
        Axis labels.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.
    colors : list, optional
        Colors for each series.
    linewidth : float
        Line width.
    grid : bool
        Whether to show grid.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)

    for i, y in enumerate(y_lists):
        color = colors[i] if colors else None
        label = labels[i] if labels else None
        ax.plot(x, y, label=label, color=color, linewidth=linewidth)

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if grid:
        ax.grid(alpha=0.3)
    if labels:
        ax.legend()
    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def scatter_plot(
    x: np.ndarray,
    y: np.ndarray,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (6, 6),
    alpha: float = 0.5,
) -> plt.Figure:
    """
    Create a scatter plot.

    Parameters
    ----------
    x, y : array-like
        X and Y values.
    title, xlabel, ylabel : str
        Labels.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.
    alpha : float
        Point transparency.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)
    ax.scatter(x, y, alpha=alpha, edgecolors="w", linewidth=0.5)

    # Add identity line
    lims = [min(min(x), min(y)), max(max(x), max(y))]
    ax.plot(lims, lims, "--", color="gray", alpha=0.8, label="Identity")
    ax.set_xlim(lims)
    ax.set_ylim(lims)

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def heatmap(
    data: np.ndarray,
    xlabels: list,
    ylabels: list,
    title: str = "",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (10, 8),
    cmap: str = HEATMAP_CMAP,
    vmin: float = -1.0,
    vmax: float = 1.0,
) -> plt.Figure:
    """
    Create a heatmap.

    Parameters
    ----------
    data : np.ndarray
        2D array of values.
    xlabels, ylabels : list
        Tick labels.
    title : str
        Plot title.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.
    cmap : str
        Colormap name.
    vmin, vmax : float
        Color scale limits.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax)

    ax.set_xticks(range(len(xlabels)))
    ax.set_xticklabels(xlabels, rotation=90, fontsize=8)
    ax.set_yticks(range(len(ylabels)))
    ax.set_yticklabels(ylabels, fontsize=8)

    plt.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title(title)
    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig
