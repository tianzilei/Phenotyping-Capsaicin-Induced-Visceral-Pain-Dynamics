"""
Plotting functions for text mining results.
"""

from typing import Optional, Tuple

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import seaborn as sns

from analysis.constants import (
    HEATMAP_CMAP,
    NODE_COLOR_DISEASE,
    NODE_COLOR_REGION,
    NODE_COLOR_SYMPTOM,
)
from analysis.visualization.plots import save_figure


def plot_tripartite_network(
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (12, 8),
) -> plt.Figure:
    """
    Plot tripartite network graph.

    Parameters
    ----------
    nodes_df : pd.DataFrame
        Node table with columns: node_type, name, count.
    edges_df : pd.DataFrame
        Edge table with columns: edge_type, source, target, weight.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    G = nx.Graph()

    # Add nodes with type attribute
    for _, node in nodes_df.iterrows():
        G.add_node(node["name"], node_type=node["node_type"], count=node["count"])

    # Add edges
    for _, edge in edges_df.iterrows():
        G.add_edge(edge["source"], edge["target"], weight=edge["weight"])

    # Layout
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

    fig, ax = plt.subplots(figsize=figsize)

    # Color by node type
    color_map = {
        "symptom": NODE_COLOR_SYMPTOM,
        "region": NODE_COLOR_REGION,
        "disease": NODE_COLOR_DISEASE,
    }
    node_colors = [
        color_map.get(G.nodes[n].get("node_type", ""), "gray") for n in G.nodes()
    ]

    # Size by count
    node_sizes = [G.nodes[n].get("count", 1) * 100 for n in G.nodes()]

    nx.draw_networkx_nodes(
        G, pos, node_color=node_colors, node_size=node_sizes, alpha=0.8, ax=ax
    )
    nx.draw_networkx_edges(G, pos, alpha=0.3, ax=ax)
    nx.draw_networkx_labels(G, pos, font_size=8, ax=ax)

    ax.set_title("Tripartite Network: Symptom-Region-Disease")
    ax.axis("off")
    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig


def plot_cooccurrence_heatmaps(
    matrices: dict,
    save_path: Optional[str] = None,
    figsize_per: Tuple[int, int] = (8, 6),
) -> plt.Figure:
    """
    Plot co-occurrence heatmaps.

    Parameters
    ----------
    matrices : dict
        Dictionary with keys: symptom_region, symptom_disease, region_disease.
    save_path : str, optional
        Path to save figure.
    figsize_per : tuple
        Figure size per heatmap.

    Returns
    -------
    matplotlib.figure.Figure
    """
    valid_matrices = {k: v for k, v in matrices.items() if len(v) > 0}
    n = len(valid_matrices)

    if n == 0:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        return fig

    fig, axes = plt.subplots(1, n, figsize=(figsize_per[0] * n, figsize_per[1]))
    if n == 1:
        axes = [axes]

    titles = {
        "symptom_region": "Symptom-Region Co-occurrence",
        "symptom_disease": "Symptom-Disease Association",
        "region_disease": "Region-Disease Association",
    }

    for ax, (key, matrix) in zip(axes, valid_matrices.items()):
        sns.heatmap(matrix, annot=True, fmt=".1f", cmap=HEATMAP_CMAP, ax=ax)
        ax.set_title(titles.get(key, key))
        ax.tick_params(axis="x", rotation=45)
        ax.tick_params(axis="y", rotation=0)

    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig
