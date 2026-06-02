"""
Plotting functions for network fusion results.
"""

import os
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

from analysis.constants import (
    CLUSTER_COLORS,
    NODE_COLOR_DISEASE,
    NODE_COLOR_REGION,
    NODE_COLOR_SYMPTOM,
    SECONDARY_COLOR,
    TERTIARY_COLOR,
)
from analysis.visualization.labels import (
    pretty_cluster,
    short_disease,
    short_region,
    short_symptom,
)
from analysis.visualization.plots import save_figure


def plot_cluster_sankey(
    cluster_symptom_df: pd.DataFrame,
    cluster_region_df: pd.DataFrame,
    cluster_disease_df: pd.DataFrame,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (1000, 600),
) -> None:
    """
    Plot 4-layer Sankey diagram: cluster -> symptom -> region -> disease.

    Parameters
    ----------
    cluster_symptom_df : pd.DataFrame
        Cluster-symptom weights.
    cluster_region_df : pd.DataFrame
        Cluster-region weights.
    cluster_disease_df : pd.DataFrame
        Cluster-disease weights.
    save_path : str, optional
        Path to save HTML file.
    figsize : tuple
        Figure size in pixels.
    """
    import plotly.graph_objects as go

    # Prepare nodes
    clusters = sorted(cluster_symptom_df["cluster"].unique())
    symptoms = cluster_symptom_df["symptom"].unique().tolist()
    regions = cluster_region_df["region"].unique().tolist()
    diseases = cluster_disease_df["disease"].unique().tolist()

    all_labels = (
        [pretty_cluster(c) for c in clusters]
        + [short_symptom(s) for s in symptoms]
        + [short_region(r) for r in regions]
        + [short_disease(d) for d in diseases]
    )

    # Node colors
    node_colors = (
        CLUSTER_COLORS[: len(clusters)]
        + [NODE_COLOR_SYMPTOM] * len(symptoms)
        + [NODE_COLOR_REGION] * len(regions)
        + [NODE_COLOR_DISEASE] * len(diseases)
    )

    # Build links
    sources, targets, values, link_colors = [], [], [], []

    # Cluster -> Symptom links
    for _, row in cluster_symptom_df.iterrows():
        c_idx = clusters.index(row["cluster"])
        s_idx = len(clusters) + symptoms.index(row["symptom"])
        sources.append(c_idx)
        targets.append(s_idx)
        values.append(row["weight"])
        link_colors.append(CLUSTER_COLORS[row["cluster"] % len(CLUSTER_COLORS)] + "80")

    # Symptom -> Region links
    for _, row in cluster_region_df.iterrows():
        s_idx = len(clusters) + symptoms.index(row["symptom"])
        r_idx = len(clusters) + len(symptoms) + regions.index(row["region"])
        sources.append(s_idx)
        targets.append(r_idx)
        values.append(row["weight"])
        link_colors.append(SECONDARY_COLOR + "80")

    # Symptom -> Disease links
    for _, row in cluster_disease_df.iterrows():
        s_idx = len(clusters) + symptoms.index(row["symptom"])
        d_idx = (
            len(clusters)
            + len(symptoms)
            + len(regions)
            + diseases.index(row["disease"])
        )
        sources.append(s_idx)
        targets.append(d_idx)
        values.append(row["weight"])
        link_colors.append(TERTIARY_COLOR + "80")

    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    pad=15,
                    thickness=20,
                    line=dict(color="black", width=0.5),
                    label=all_labels,
                    color=node_colors,
                ),
                link=dict(
                    source=sources, target=targets, value=values, color=link_colors
                ),
            )
        ]
    )

    fig.update_layout(
        title_text="Cluster -> Symptom -> Region -> Disease", font_size=10
    )

    if save_path:
        os.makedirs(
            os.path.dirname(save_path) if os.path.dirname(save_path) else ".",
            exist_ok=True,
        )
        fig.write_html(save_path)


def plot_cluster_subnetworks(
    cluster_symptom_df: pd.DataFrame,
    cluster_region_df: pd.DataFrame,
    cluster_disease_df: pd.DataFrame,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (16, 4),
) -> plt.Figure:
    """
    Plot per-cluster subnetwork diagrams.

    Parameters
    ----------
    cluster_symptom_df : pd.DataFrame
        Cluster-symptom weights.
    cluster_region_df : pd.DataFrame
        Cluster-region weights.
    cluster_disease_df : pd.DataFrame
        Cluster-disease weights.
    save_path : str, optional
        Path to save figure.
    figsize : tuple
        Figure size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    clusters = sorted(cluster_symptom_df["cluster"].unique())
    n_clusters = len(clusters)

    fig, axes = plt.subplots(1, n_clusters, figsize=figsize)
    if n_clusters == 1:
        axes = [axes]

    for ax, cluster in zip(axes, clusters):
        G = nx.Graph()

        # Add cluster node
        G.add_node(pretty_cluster(cluster), node_type="cluster")

        # Add symptom nodes and edges
        c_symptoms = cluster_symptom_df[cluster_symptom_df["cluster"] == cluster]
        for _, row in c_symptoms.iterrows():
            s_name = short_symptom(row["symptom"])
            G.add_node(s_name, node_type="symptom")
            G.add_edge(pretty_cluster(cluster), s_name, weight=row["weight"])

        # Add region nodes and edges
        c_regions = cluster_region_df[cluster_region_df["cluster"] == cluster]
        for _, row in c_regions.iterrows():
            r_name = short_region(row["region"])
            G.add_node(r_name, node_type="region")
            # Connect to top symptom
            if len(c_symptoms) > 0:
                top_symptom = short_symptom(c_symptoms.iloc[0]["symptom"])
                G.add_edge(top_symptom, r_name, weight=row["weight"])

        # Add disease nodes and edges
        c_diseases = cluster_disease_df[cluster_disease_df["cluster"] == cluster]
        for _, row in c_diseases.iterrows():
            d_name = short_disease(row["disease"])
            G.add_node(d_name, node_type="disease")
            # Connect to top symptom
            if len(c_symptoms) > 0:
                top_symptom = short_symptom(c_symptoms.iloc[0]["symptom"])
                G.add_edge(top_symptom, d_name, weight=row["weight"])

        # Layout
        pos = nx.spring_layout(G, k=1.5, seed=42)

        # Color by type
        color_map = {
            "cluster": CLUSTER_COLORS[0],
            "symptom": NODE_COLOR_SYMPTOM,
            "region": NODE_COLOR_REGION,
            "disease": NODE_COLOR_DISEASE,
        }
        node_colors = [
            color_map.get(G.nodes[n].get("node_type", ""), "gray") for n in G.nodes()
        ]

        nx.draw_networkx_nodes(
            G, pos, node_color=node_colors, node_size=500, alpha=0.9, ax=ax
        )
        nx.draw_networkx_edges(G, pos, alpha=0.5, ax=ax)
        nx.draw_networkx_labels(G, pos, font_size=7, ax=ax)

        ax.set_title(pretty_cluster(cluster))
        ax.axis("off")

    fig.tight_layout()

    if save_path:
        save_figure(fig, save_path)

    return fig
