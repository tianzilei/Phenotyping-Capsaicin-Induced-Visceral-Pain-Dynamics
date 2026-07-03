"""
Network fusion: cluster-specific phenotype scoring and transitive paths.
"""

from itertools import product

from typing import Dict, Optional, Tuple

import pandas as pd

from analysis.constants import REGION_CODE_MAP, SYMPTOM_CODE_MAP
from analysis.parsing import map_codes, parse_compact_codes, parse_region_codes


def compute_cluster_symptom_weights(
    cluster_df: pd.DataFrame,
    cluster_col: str = "cluster",
    id_col: str = "ID",
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
    if cluster_col not in cluster_df.columns:
        raise ValueError(f"Expected cluster column '{cluster_col}' in fusion input.")

    if id_col in cluster_df.columns:
        cluster_sizes = cluster_df.groupby(cluster_col)[id_col].nunique()
    else:
        cluster_sizes = cluster_df.groupby(cluster_col).size()

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


def build_grouped_sankey_links(
    clustered_df: pd.DataFrame,
    rome_df: pd.DataFrame,
    cluster_col: str = "cluster",
    id_col: str = "ID",
    symptom_col: str = "Symptom_codes",
    region_col: str = "Region_code",
    rome_id_col: str = "participant_id",
    top_disease_col: str = "top_disease",
    symptom_code_map: Optional[Dict] = None,
    region_code_map: Optional[Dict] = None,
    top_n_symptoms: Optional[int] = None,
    top_n_regions: Optional[int] = None,
    top_n_diseases: Optional[int] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Build grouped Sankey link tables from participant-level cluster and symptom data.

    The flow unit is an expanded participant-level symptom-region pair occurrence.
    Each participant contributes one unit for every observed symptom-region
    combination, linked to the participant's top Rome IV-informed category.

    Parameters
    ----------
    clustered_df : pd.DataFrame
        Participant-level data with cluster, symptom-code, and region-code columns.
    rome_df : pd.DataFrame
        Participant-level Rome IV mapping with top disease assignments.
    cluster_col : str
        Cluster label column in ``clustered_df``.
    id_col : str
        Participant identifier column in ``clustered_df``.
    symptom_col : str
        Symptom-code column in ``clustered_df``.
    region_col : str
        Region-code column in ``clustered_df``.
    rome_id_col : str
        Participant identifier column in ``rome_df``.
    top_disease_col : str
        Top Rome IV-informed category column in ``rome_df``.
    symptom_code_map : dict, optional
        Symptom code mapping. Uses project defaults if None.
    region_code_map : dict, optional
        Region code mapping. Uses project defaults if None.
    top_n_symptoms : int, optional
        Number of symptom nodes to keep before grouping the remainder. If None,
        keep all observed symptom nodes.
    top_n_regions : int, optional
        Number of region nodes to keep before grouping the remainder. If None,
        keep all observed region nodes.
    top_n_diseases : int, optional
        Number of matched disease nodes to keep before grouping the remainder.
        ``No Match`` is retained separately regardless of rank. If None, keep
        all observed Rome-pattern nodes.

    Returns
    -------
    tuple of pd.DataFrame
        ``(cluster_symptom_df, symptom_region_df, region_disease_df)`` with a
        shared ``value`` count column.
    """
    if symptom_code_map is None:
        symptom_code_map = SYMPTOM_CODE_MAP
    if region_code_map is None:
        region_code_map = REGION_CODE_MAP

    merged = clustered_df[
        [id_col, cluster_col, symptom_col, region_col]
    ].merge(
        rome_df[[rome_id_col, top_disease_col]],
        left_on=id_col,
        right_on=rome_id_col,
        how="left",
    )

    records = []
    for _, row in merged.iterrows():
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
        disease = row.get(top_disease_col, "No Match")
        disease = disease if isinstance(disease, str) and disease.strip() else "No Match"

        if not symptoms or not regions:
            continue

        for symptom, region in product(symptoms, regions):
            records.append(
                {
                    "cluster": row[cluster_col],
                    "symptom": symptom,
                    "region": region,
                    "disease": disease,
                }
            )

    expanded_df = pd.DataFrame(records)
    if expanded_df.empty:
        empty = pd.DataFrame(columns=["source", "target", "value"])
        return empty, empty, empty

    def _keep_labels(
        counts: pd.Series,
        top_n: Optional[int],
    ) -> list:
        if top_n is None or top_n <= 0 or top_n >= len(counts):
            return counts.index.tolist()
        return counts.head(top_n).index.tolist()

    top_symptoms = _keep_labels(expanded_df["symptom"].value_counts(), top_n_symptoms)
    top_regions = _keep_labels(expanded_df["region"].value_counts(), top_n_regions)
    disease_counts = expanded_df["disease"].value_counts()
    if top_n_diseases is None or top_n_diseases <= 0:
        matched_diseases = disease_counts.index.tolist()
    else:
        matched_diseases = [
            d for d in disease_counts.index.tolist() if d != "No Match"
        ][:top_n_diseases]
        if "No Match" in disease_counts.index:
            matched_diseases.append("No Match")

    symptom_other = "Other symptoms"
    region_other = "Other regions"
    disease_other = "Other Rome patterns"

    expanded_df["symptom_group"] = expanded_df["symptom"].where(
        expanded_df["symptom"].isin(top_symptoms), symptom_other
    )
    expanded_df["region_group"] = expanded_df["region"].where(
        expanded_df["region"].isin(top_regions), region_other
    )
    expanded_df["disease_group"] = expanded_df["disease"].where(
        expanded_df["disease"].isin(matched_diseases), disease_other
    )

    cluster_symptom_df = (
        expanded_df.groupby(["cluster", "symptom_group"])
        .size()
        .reset_index(name="value")
        .rename(columns={"cluster": "source", "symptom_group": "target"})
    )
    symptom_region_df = (
        expanded_df.groupby(["symptom_group", "region_group"])
        .size()
        .reset_index(name="value")
        .rename(columns={"symptom_group": "source", "region_group": "target"})
    )
    region_disease_df = (
        expanded_df.groupby(["region_group", "disease_group"])
        .size()
        .reset_index(name="value")
        .rename(columns={"region_group": "source", "disease_group": "target"})
    )

    cluster_symptom_df = cluster_symptom_df.sort_values(
        ["source", "value", "target"], ascending=[True, False, True]
    ).reset_index(drop=True)
    symptom_region_df = symptom_region_df.sort_values(
        ["value", "source", "target"], ascending=[False, True, True]
    ).reset_index(drop=True)
    region_disease_df = region_disease_df.sort_values(
        ["value", "source", "target"], ascending=[False, True, True]
    ).reset_index(drop=True)

    return cluster_symptom_df, symptom_region_df, region_disease_df
