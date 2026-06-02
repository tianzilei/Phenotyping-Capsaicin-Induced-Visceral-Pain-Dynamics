"""
Matplotlib style configuration for publication-quality output.
"""

import matplotlib.pyplot as plt
import seaborn as sns


def set_publication_style():
    """
    Configure matplotlib for publication-quality figures.

    Sets font sizes, line widths, tick parameters, and other style options
    suitable for journal publications. Uses seaborn's magma palette.
    """
    sns.set_theme(style="ticks", palette="magma")
    plt.rcParams.update(
        {
            # Figure
            "figure.figsize": (8, 6),
            "figure.dpi": 150,
            "figure.facecolor": "white",
            # Font
            "font.family": "sans-serif",
            "font.size": 12,
            "axes.titlesize": 14,
            "axes.labelsize": 12,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
            # Lines
            "lines.linewidth": 2.0,
            "lines.markersize": 6,
            # Axes
            "axes.linewidth": 1.0,
            "axes.grid": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            # Grid
            "grid.alpha": 0.3,
            "grid.linewidth": 0.5,
            # Legend
            "legend.frameon": True,
            "legend.framealpha": 0.8,
            # Savefig
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.1,
        }
    )


def reset_style():
    """Reset matplotlib to default style."""
    plt.rcParams.update(plt.rcParamsDefault)
