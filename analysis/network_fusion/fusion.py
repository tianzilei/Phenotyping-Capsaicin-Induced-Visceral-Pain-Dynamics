"""
Network fusion: cluster-specific phenotype scoring and transitive paths.
"""

from typing import Dict, Optional, Tuple

import pandas as pd

from analysis.constants import REGION_CODE_MAP, SYMPTOM_CODE_MAP
from analysis.parsing import map_codes, parse_compact_codes, parse_region_codes


def compute_cluster_symptom_weights(
    cluster_df: pd.DataFrame,
    cluster_col: str = "cluster",
    symptom_col: str = "Symptom",
    region_col: str = "Region",
    symptom_code_map: Optional[Dict] = None,
    region_code_map: Optional[Dict] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute cluster-symptom and cluster-region weights.

    Parameters
    ----------
    cluster_df : pd.DataFrame
        DataFrame with cluster assignments and symptom/region codes.
    cluster_col : str
        Column name for cluster assignments.
    symptom_col : str
        Column name for symptom codes.
    region_col : str
        Column name for region codes.
    symptom_code_map : dict, optional
        Symptom code to label mapping.
    region_code_map : dict, optional
        Region code to label mapping.

    Returns
    -------
    tuple of (pd.DataFrame, pd.DataFrame)
        (cluster_symptom_df, cluster_region_df) with columns:
        cluster, symptom/region, weight.
    """
    if symptom_code_map is None:
        symptom_code_map = SYMPTOM_CODE_MAP
    if region_code_map is None:
        region_code_map = REGION_CODE_MAP

    # Parse symptoms and regions for each subject
    records = []
    for _, row in cluster_df.iterrows():
        cluster = row[cluster_col]
        symptoms = map_codes(
            parse_compact_codes(
                str(row.get(symptom_col, "")), valid_codes=set(symptom_code_map.keys())
            ),
            symptom_code_map,
        )
        regions = map_codes(
            parse_region_codes(
                str(row.get(region_col, "")), valid_codes=set(region_code_map.keys())
            ),
            region_code_map,
        )

        for s in symptoms:
            records.append({"cluster": cluster, "symptom": s})
        for r in regions:
            records.append({"cluster": cluster, "region": r})

    records_df = pd.DataFrame(records)

    # Compute weights (proportion of subjects in cluster reporting each symptom/region)
    cluster_sizes = records_df.groupby("cluster").size()

    if len(cluster_sizes) == 0:
        return pd.DataFrame(columns=["cluster", "symptom", "weight"]), pd.DataFrame(
            columns=["cluster", "region", "weight"]
        )

    cluster_symptom = (
        records_df.groupby(["cluster", "symptom"]).size().reset_index(name="count")
    )
    cluster_symptom["weight"] = cluster_symptom.apply(
        lambda row: row["count"] / cluster_sizes.get(row["cluster"], 1), axis=1
    )

    cluster_region = (
        records_df.groupby(["cluster", "region"]).size().reset_index(name="count")
    )
    cluster_region["weight"] = cluster_region.apply(
        lambda row: row["count"] / cluster_sizes.get(row["cluster"], 1), axis=1
    )

    return cluster_symptom[["cluster", "symptom", "weight"]], cluster_region[
        ["cluster", "region", "weight"]
    ]


def compute_transitive_scores(
    cluster_source_df: pd.DataFrame,
    source_col: str,
    target_lookup: Dict[str, list],
    source_key: str = "symptom",
    target_key: str = "region",
) -> pd.DataFrame:
    """
    Compute transitive scores: cluster -> source -> target.

    Parameters
    ----------
    cluster_source_df : pd.DataFrame
        Cluster-source weights with columns: cluster, source_col, weight.
    source_col : str
        Column name for source (e.g., 'symptom').
    target_lookup : dict
        Mapping from source to list of targets.
    source_key : str
        Name for source column in output.
    target_key : str
        Name for target column in output.

    Returns
    -------
    pd.DataFrame
        Transitive scores with columns: cluster, target, weight.
    """
    records = []

    for _, row in cluster_source_df.iterrows():
        cluster = row["cluster"]
        source = row[source_col]
        weight = row["weight"]

        targets = target_lookup.get(source, [])
        for t in targets:
            records.append({"cluster": cluster, target_key: t, "weight": weight})

    if not records:
        return pd.DataFrame(columns=["cluster", target_key, "weight"])

    df = pd.DataFrame(records)

    # Aggregate by cluster and target
    result = df.groupby(["cluster", target_key])["weight"].sum().reset_index()

    return result


def build_symptom_to_region_lookup(
    edges_df: pd.DataFrame,
) -> Dict[str, list]:
    """
    Build symptom -> region lookup from tripartite edges.

    Parameters
    ----------
    edges_df : pd.DataFrame
        Edges DataFrame with edge_type == 'symptom_region'.

    Returns
    -------
    dict
        Mapping from symptom to list of regions.
    """
    lookup = {}
    subset = edges_df[edges_df["edge_type"] == "symptom_region"]

    for _, row in subset.iterrows():
        symptom = row["source"]
        region = row["target"]
        if symptom not in lookup:
            lookup[symptom] = []
        lookup[symptom].append(region)

    return lookup


def build_symptom_to_disease_lookup(
    edges_df: pd.DataFrame,
) -> Dict[str, list]:
    """
    Build symptom -> disease lookup from tripartite edges.

    Parameters
    ----------
    edges_df : pd.DataFrame
        Edges DataFrame with edge_type == 'symptom_disease'.

    Returns
    -------
    dict
        Mapping from symptom to list of diseases.
    """
    lookup = {}
    subset = edges_df[edges_df["edge_type"] == "symptom_disease"]

    for _, row in subset.iterrows():
        symptom = row["source"]
        disease = row["target"]
        if symptom not in lookup:
            lookup[symptom] = []
        lookup[symptom].append(disease)

    return lookup


def build_full_path_table(
    cluster_symptom_df: pd.DataFrame,
    symptom_to_region: Dict[str, list],
    symptom_to_disease: Dict[str, list],
) -> pd.DataFrame:
    """
    Build full 4-hop path table: cluster -> symptom -> region -> disease.

    Parameters
    ----------
    cluster_symptom_df : pd.DataFrame
        Cluster-symptom weights.
    symptom_to_region : dict
        Symptom -> region lookup.
    symptom_to_disease : dict
        Symptom -> disease lookup.

    Returns
    -------
    pd.DataFrame
        Full path table.
    """
    # Compute cluster-region via transitivity
    cluster_region_df = compute_transitive_scores(
        cluster_symptom_df,
        "symptom",
        symptom_to_region,
        source_key="symptom",
        target_key="region",
    )

    # Compute cluster-disease via transitivity
    cluster_disease_df = compute_transitive_scores(
        cluster_symptom_df,
        "symptom",
        symptom_to_disease,
        source_key="symptom",
        target_key="disease",
    )

    return cluster_region_df, cluster_disease_df
