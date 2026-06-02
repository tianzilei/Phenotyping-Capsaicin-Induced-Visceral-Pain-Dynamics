"""
Unified table generator for manuscript and supplementary material.
"""

import os
from typing import Optional

import pandas as pd

from analysis.constants import METRICS_DIR
from analysis.data_loader import load_unified_baseline
from analysis.tables.baseline import generate_baseline_table
from analysis.tables.network import (
    generate_network_nodes_table,
    generate_region_disease_table,
    generate_symptom_disease_table,
    generate_symptom_region_table,
)
from analysis.tables.prediction import generate_prediction_table
from analysis.tables.safety import generate_adverse_events_table


def generate_all_tables(
    baseline_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> dict:
    """
    Generate all manuscript and supplementary tables.

    Parameters
    ----------
    baseline_path : str, optional
        Path to subject_baseline_info.csv. Uses default if None.
    output_dir : str, optional
        Directory to save Markdown files. Uses data/metrics/ if None.

    Returns
    -------
    dict
        Dictionary mapping table name to Markdown string.
    """
    if output_dir is None:
        output_dir = METRICS_DIR
    os.makedirs(output_dir, exist_ok=True)

    # Load data
    baseline_df = load_unified_baseline(baseline_path)
    edges_df = pd.read_csv(os.path.join(METRICS_DIR, "textmining_tripartite_edges.csv"))
    pred_fold_df = pd.read_csv(
        os.path.join(METRICS_DIR, "prediction_classification_fold_metrics.csv")
    )

    tables = {}

    # Table 1: Baseline characteristics
    tables["table1_baseline"] = generate_baseline_table(baseline_df)

    # Table S1: Top symptom-region associations
    tables["table_s1_symptom_region"] = generate_symptom_region_table(edges_df)

    # Table S2: Top network nodes
    tables["table_s2_network_nodes"] = generate_network_nodes_table(edges_df)

    # Table S2b: Region-disease
    tables["table_s2b_region_disease"] = generate_region_disease_table(edges_df)

    # Table S2c: Symptom-disease
    tables["table_s2c_symptom_disease"] = generate_symptom_disease_table(edges_df)

    # Table S3: Prediction performance
    tables["table_s3_prediction"] = generate_prediction_table(pred_fold_df)

    # Table S4: Adverse events
    tables["table_s4_adverse_events"] = generate_adverse_events_table()

    # Save to files
    for name, content in tables.items():
        filepath = os.path.join(output_dir, f"{name}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Saved: {filepath}")

    # Also save a combined file
    combined_path = os.path.join(output_dir, "all_tables.md")
    with open(combined_path, "w", encoding="utf-8") as f:
        f.write("# Manuscript Tables\n\n")
        for name, content in tables.items():
            f.write(content)
            f.write("\n---\n\n")
    print(f"Saved combined: {combined_path}")

    return tables
