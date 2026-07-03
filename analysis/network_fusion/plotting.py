"""
Plotting functions for network fusion results.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional, Tuple

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

if TYPE_CHECKING:
    import plotly.graph_objects as go


def _require_plotly():
    try:
        import plotly.graph_objects as go
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "plotly is required for network Sankey figures. "
            "Install the packages from requirements.txt before generating these plots."
        ) from exc
    return go


def _hex_to_rgba(color: str, alpha: float) -> str:
    """Convert a hex color like '#aabbcc' to plotly rgba()."""
    color = color.lstrip("#")
    if len(color) != 6:
        return f"rgba(128,128,128,{alpha})"
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


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
    go = _require_plotly()

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


def plot_grouped_cluster_sankey(
    cluster_symptom_df: pd.DataFrame,
    symptom_region_df: pd.DataFrame,
    region_disease_df: pd.DataFrame,
    save_path: Optional[str] = None,
    cluster_label_map: Optional[dict] = None,
    disease_participant_counts: Optional[dict] = None,
    total_participants: Optional[int] = None,
    width: int = 2200,
    height: Optional[int] = None,
) -> "go.Figure":
    """
    Plot a grouped 4-layer Sankey diagram: phenotype -> symptom -> region -> Rome pattern.

    Parameters
    ----------
    cluster_symptom_df : pd.DataFrame
        Link table with columns: source, target, value. Source is cluster ID.
    symptom_region_df : pd.DataFrame
        Link table with columns: source, target, value.
    region_disease_df : pd.DataFrame
        Link table with columns: source, target, value.
    save_path : str, optional
        Path to save a static image or HTML file.
    cluster_label_map : dict, optional
        Mapping from numeric cluster IDs to display labels.
    disease_participant_counts : dict, optional
        Participant-level counts for displayed Rome-pattern categories.
    total_participants : int, optional
        Denominator used for participant-level percentages in disease labels.
    width : int
        Figure width in pixels.
    height : int
        Figure height in pixels.
    """
    go = _require_plotly()

    if cluster_label_map is None:
        cluster_label_map = {}

    def _ordered_labels(df: pd.DataFrame, label_col: str, sink_labels: set) -> list:
        totals = df.groupby(label_col)["value"].sum().sort_values(ascending=False)
        primary = [label for label in totals.index.tolist() if label not in sink_labels]
        sinks = [label for label in sink_labels if label in totals.index]
        return primary + sinks

    cluster_ids = sorted(cluster_symptom_df["source"].unique().tolist())
    symptom_labels = _ordered_labels(cluster_symptom_df, "target", {"Other symptoms"})
    region_labels = _ordered_labels(symptom_region_df, "target", {"Other regions"})
    disease_labels = _ordered_labels(
        region_disease_df, "target", {"No Match", "Other Rome patterns"}
    )

    cluster_display = [
        cluster_label_map.get(c, pretty_cluster(int(c)) if str(c).isdigit() else str(c))
        for c in cluster_ids
    ]
    symptom_display = [
        short_symptom(s) if s != "Other symptoms" else s for s in symptom_labels
    ]
    region_display = [
        short_region(r) if r != "Other regions" else r for r in region_labels
    ]
    disease_flow_totals = region_disease_df.groupby("target")["value"].sum().to_dict()
    total_flow = sum(disease_flow_totals.values()) or 1
    other_disease_participant_n = None
    if disease_participant_counts is not None:
        displayed_exact_diseases = {
            disease for disease in disease_labels if disease != "Other Rome patterns"
        }
        other_disease_participant_n = sum(
            count
            for disease, count in disease_participant_counts.items()
            if disease not in displayed_exact_diseases
        )
    disease_display = []
    for disease in disease_labels:
        base = (
            short_disease(disease)
            if disease not in {"No Match", "Other Rome patterns"}
            else disease
        )
        flow = int(disease_flow_totals.get(disease, 0))
        flow_pct = 100.0 * flow / total_flow
        if disease_participant_counts is not None and total_participants:
            if (
                disease == "Other Rome patterns"
                and other_disease_participant_n is not None
            ):
                participant_n = int(other_disease_participant_n)
            else:
                participant_n = int(disease_participant_counts.get(disease, 0))
            participant_pct = 100.0 * participant_n / total_participants
            detail = f"n={participant_n} ({participant_pct:.1f}%) | flow={flow}"
        else:
            detail = f"flow={flow} ({flow_pct:.1f}%)"
        disease_display.append(f"{base}<br>{detail}")

    labels = cluster_display + symptom_display + region_display + disease_display
    node_colors = (
        [CLUSTER_COLORS[i % len(CLUSTER_COLORS)] for i in range(len(cluster_ids))]
        + [NODE_COLOR_SYMPTOM] * len(symptom_labels)
        + [NODE_COLOR_REGION] * len(region_labels)
        + [NODE_COLOR_DISEASE] * len(disease_labels)
    )

    cluster_index = {c: i for i, c in enumerate(cluster_ids)}
    symptom_index = {s: len(cluster_ids) + i for i, s in enumerate(symptom_labels)}
    region_index = {
        r: len(cluster_ids) + len(symptom_labels) + i
        for i, r in enumerate(region_labels)
    }
    disease_index = {
        d: len(cluster_ids) + len(symptom_labels) + len(region_labels) + i
        for i, d in enumerate(disease_labels)
    }

    if height is None:
        max_layer_nodes = max(
            len(cluster_ids),
            len(symptom_labels),
            len(region_labels),
            len(disease_labels),
        )
        height = max(1100, 220 + max_layer_nodes * 120)

    sources = []
    targets = []
    values = []
    link_colors = []

    for _, row in cluster_symptom_df.iterrows():
        cluster_id = row["source"]
        sources.append(cluster_index[cluster_id])
        targets.append(symptom_index[row["target"]])
        values.append(row["value"])
        link_colors.append(
            _hex_to_rgba(CLUSTER_COLORS[int(cluster_id) % len(CLUSTER_COLORS)], 0.45)
        )

    for _, row in symptom_region_df.iterrows():
        sources.append(symptom_index[row["source"]])
        targets.append(region_index[row["target"]])
        values.append(row["value"])
        link_colors.append(_hex_to_rgba(NODE_COLOR_SYMPTOM, 0.35))

    for _, row in region_disease_df.iterrows():
        sources.append(region_index[row["source"]])
        targets.append(disease_index[row["target"]])
        values.append(row["value"])
        disease = row["target"]
        max_flow = max(disease_flow_totals.values()) if disease_flow_totals else 1
        alpha = 0.30 + 0.40 * (row["value"] / max_flow)
        disease_color_map = {
            "Biliary Pain-like": "#f28e2b",
            "Functional Abdominal Bloating/Distension-like": "#ffb55a",
            "Irritable Bowel Syndrome-like": "#ff9d76",
            "No Match": "#f3b37e",
            "Other Rome patterns": "#f7caa2",
        }
        link_colors.append(
            _hex_to_rgba(disease_color_map.get(disease, NODE_COLOR_DISEASE), alpha)
        )

    def _layer_positions(n_items: int, x_pos: float) -> Tuple[list, list]:
        if n_items == 1:
            return [x_pos], [0.5]
        top_pad = 0.12
        bottom_pad = 0.12
        usable_height = 1 - top_pad - bottom_pad
        y_values = [
            top_pad + i * (usable_height / (n_items - 1)) for i in range(n_items)
        ]
        return [x_pos] * n_items, y_values

    x_vals = []
    y_vals = []
    for n_items, x_pos in [
        (len(cluster_ids), 0.06),
        (len(symptom_labels), 0.31),
        (len(region_labels), 0.59),
        (len(disease_labels), 0.86),
    ]:
        x_layer, y_layer = _layer_positions(n_items, x_pos)
        x_vals.extend(x_layer)
        y_vals.extend(y_layer)

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="fixed",
                domain=dict(x=[0.06, 0.94], y=[0.10, 0.90]),
                node=dict(
                    pad=18,
                    thickness=16,
                    line=dict(color="rgba(40,40,40,0.35)", width=0.7),
                    label=labels,
                    color=node_colors,
                    x=x_vals,
                    y=y_vals,
                    hovertemplate="%{label}<extra></extra>",
                ),
                link=dict(
                    source=sources,
                    target=targets,
                    value=values,
                    color=link_colors,
                    hovertemplate="Count: %{value}<extra></extra>",
                ),
            )
        ]
    )
    fig.update_layout(
        title_text="Temporal phenotype to symptom-region-Rome IV flow structure",
        title=dict(
            x=0.5,
            y=0.985,
            xanchor="center",
            yanchor="top",
            font=dict(size=28, color="#222"),
        ),
        font=dict(size=18, color="#222"),
        paper_bgcolor="white",
        plot_bgcolor="white",
        width=width,
        height=height,
        margin=dict(l=35, r=35, t=105, b=45),
        annotations=[
            dict(
                x=0.06,
                y=0.94,
                xref="paper",
                yref="paper",
                text="Phenotype",
                showarrow=False,
                font=dict(size=18, color="#444"),
                xanchor="left",
            ),
            dict(
                x=0.31,
                y=0.94,
                xref="paper",
                yref="paper",
                text="Symptoms",
                showarrow=False,
                font=dict(size=18, color="#444"),
                xanchor="left",
            ),
            dict(
                x=0.59,
                y=0.94,
                xref="paper",
                yref="paper",
                text="Regions",
                showarrow=False,
                font=dict(size=18, color="#444"),
                xanchor="left",
            ),
            dict(
                x=0.86,
                y=0.94,
                xref="paper",
                yref="paper",
                text="Rome IV pattern",
                showarrow=False,
                font=dict(size=18, color="#444"),
                xanchor="left",
            ),
        ],
    )

    if save_path:
        os.makedirs(
            os.path.dirname(save_path) if os.path.dirname(save_path) else ".",
            exist_ok=True,
        )
        if save_path.lower().endswith(".html"):
            fig.write_html(save_path)
        else:
            fig.write_image(save_path, width=width, height=height, scale=2)

    return fig


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
