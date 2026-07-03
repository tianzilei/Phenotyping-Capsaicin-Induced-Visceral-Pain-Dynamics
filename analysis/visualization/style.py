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
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.5,
            "legend.title_fontsize": 9,
            # Lines
            "lines.linewidth": 1.8,
            "lines.markersize": 4.5,
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
            "legend.framealpha": 0.75,
            # Savefig
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.1,
        }
    )


def reset_style():
    """Reset matplotlib to default style."""
    plt.rcParams.update(plt.rcParamsDefault)
