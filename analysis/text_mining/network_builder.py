"""
Tripartite network construction: symptom-region-disease edges, nodes, matrices.
"""

from collections import Counter
from typing import Dict, Optional, Tuple

import pandas as pd

from analysis.rome_rules import ROME_RULES


def build_tripartite_edges(
    rome_mapping_df: pd.DataFrame,
    rome_rules: Optional[Dict] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build tripartite edges (symptom<->region, symptom<->disease, region<->disease).

    Parameters
    ----------
    rome_mapping_df : pd.DataFrame
        Participant-level Rome IV mapping from build_participant_rome_mapping().
    rome_rules : dict, optional
        Rome IV rules dictionary.

    Returns
    -------
    tuple of (pd.DataFrame, pd.DataFrame)
        (edges_df, nodes_df) with columns for source, target, type, weight.
    """
    if rome_rules is None:
        rome_rules = ROME_RULES

    edge_counter = Counter()
    node_counter = Counter()

    for _, row in rome_mapping_df.iterrows():
        symptoms = row.get("symptoms", [])
        regions = row.get("regions", [])
        matches = row.get("rome_matches", [])

        # Symptom <-> Region edges
        for s in symptoms:
            for r in regions:
                edge_counter[("symptom_region", s, r)] += 1
                node_counter[("symptom", s)] += 1
                node_counter[("region", r)] += 1

        # Symptom <-> Disease edges (from Rome matches)
        for match in matches:
            disease = match["disease"]
            for s in symptoms:
                edge_counter[("symptom_disease", s, disease)] += 1
                node_counter[("symptom", s)] += 1
            for r in regions:
                edge_counter[("region_disease", r, disease)] += 1
                node_counter[("region", r)] += 1
            # Count disease node once per match per participant (not per symptom/region)
            node_counter[("disease", disease)] += 1

    # Build edges DataFrame
    edges_data = []
    for (edge_type, source, target), weight in edge_counter.items():
        edges_data.append(
            {
                "edge_type": edge_type,
                "source": source,
                "target": target,
                "weight": weight,
            }
        )

    # Build nodes DataFrame
    nodes_data = []
    for (node_type, name), count in node_counter.items():
        nodes_data.append({"node_type": node_type, "name": name, "count": count})

    return pd.DataFrame(edges_data), pd.DataFrame(nodes_data)


def build_cooccurrence_matrices(
    edges_df: pd.DataFrame,
) -> Dict[str, pd.DataFrame]:
    """
    Build co-occurrence matrices from tripartite edges.

    Parameters
    ----------
    edges_df : pd.DataFrame
        Edges DataFrame with columns: edge_type, source, target, weight.

    Returns
    -------
    dict of pd.DataFrame
        Dictionary with keys: symptom_region, symptom_disease, region_disease.
    """
    matrices = {}

    for edge_type in ["symptom_region", "symptom_disease", "region_disease"]:
        subset = edges_df[edges_df["edge_type"] == edge_type]
        if len(subset) > 0:
            pivot = subset.pivot_table(
                index="source", columns="target", values="weight", fill_value=0
            )
            matrices[edge_type] = pivot
        else:
            matrices[edge_type] = pd.DataFrame()

    return matrices


def build_node_table(edges_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build node table with counts from edges.

    Parameters
    ----------
    edges_df : pd.DataFrame
        Edges DataFrame.

    Returns
    -------
    pd.DataFrame
        Node table with columns: node_type, name, count.
    """
    node_counts = Counter()

    for _, row in edges_df.iterrows():
        source_type = row["edge_type"].split("_")[0]
        target_type = row["edge_type"].split("_")[1]

        node_counts[(source_type, row["source"])] += row["weight"]
        node_counts[(target_type, row["target"])] += row["weight"]

    nodes_data = []
    for (node_type, name), count in node_counts.items():
        nodes_data.append({"node_type": node_type, "name": name, "count": count})

    return pd.DataFrame(nodes_data)
