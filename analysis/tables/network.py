"""
Generate network-related supplementary tables:
- Table S1: Top symptom-region associations
- Table S2: Top network nodes
"""

import pandas as pd

from analysis.tables.formatter import df_to_markdown


def generate_symptom_region_table(
    edges_df: pd.DataFrame,
    top_n: int = 5,
    caption: str = (
        "Table S1. Top Symptom–Region Associations of Overall Symptom–Region Network"
    ),
) -> str:
    """
    Generate Table S1: top symptom-region edges.

    Parameters
    ----------
    edges_df : pd.DataFrame
        Tripartite edges DataFrame.
    top_n : int
        Number of top edges to include.
    caption : str
        Table caption.

    Returns
    -------
    str
        Markdown-formatted table.
    """
    sr = edges_df[edges_df["edge_type"] == "symptom_region"].copy()
    sr = sr.nlargest(top_n, "weight")[["source", "target", "weight"]]
    sr.columns = ["Symptom", "Region", "Weight"]
    return df_to_markdown(sr, caption=caption)


def generate_network_nodes_table(
    edges_df: pd.DataFrame,
    top_n: int = 5,
    caption: str = "Table S2. Top Network Nodes of Overall Symptom–Region Network",
) -> str:
    """
    Generate Table S2: top network nodes by weighted degree.

    Parameters
    ----------
    edges_df : pd.DataFrame
        Tripartite edges DataFrame.
    top_n : int
        Number of top nodes to include.
    caption : str
        Table caption.

    Returns
    -------
    str
        Markdown-formatted table.
    """
    sr = edges_df[edges_df["edge_type"] == "symptom_region"].copy()

    # Compute degree and weighted degree for each node
    node_stats = {}
    for _, row in sr.iterrows():
        for col, node_type in [("source", "symptom"), ("target", "region")]:
            name = row[col]
            key = (name, node_type)
            if key not in node_stats:
                node_stats[key] = {"degree": 0, "weighted_degree": 0.0}
            node_stats[key]["degree"] += 1
            node_stats[key]["weighted_degree"] += row["weight"]

    rows = []
    for (name, node_type), stats in node_stats.items():
        rows.append(
            {
                "Node": name,
                "Type": node_type,
                "Degree": stats["degree"],
                "Weighted Degree": stats["weighted_degree"],
            }
        )

    nodes_df = (
        pd.DataFrame(rows).sort_values("Weighted Degree", ascending=False).head(top_n)
    )
    return df_to_markdown(nodes_df, caption=caption)


def generate_region_disease_table(
    edges_df: pd.DataFrame,
    top_n: int = 10,
    caption: str = "Table S2b. Top Region–Disease Associations",
) -> str:
    """Generate top region-disease edges table."""
    rd = edges_df[edges_df["edge_type"] == "region_disease"].copy()
    rd = rd.nlargest(top_n, "weight")[["source", "target", "weight"]]
    rd.columns = ["Region", "Disease", "Weight"]
    return df_to_markdown(rd, caption=caption)


def generate_symptom_disease_table(
    edges_df: pd.DataFrame,
    top_n: int = 10,
    caption: str = "Table S2c. Top Symptom–Disease Associations",
) -> str:
    """Generate top symptom-disease edges table."""
    sd = edges_df[edges_df["edge_type"] == "symptom_disease"].copy()
    sd = sd.nlargest(top_n, "weight")[["source", "target", "weight"]]
    sd.columns = ["Symptom", "Disease", "Weight"]
    return df_to_markdown(sd, caption=caption)
