"""
Text mining: symptom/region parsing and Rome IV mapping.
"""

from typing import Dict, Optional

import pandas as pd

from analysis.constants import REGION_CODE_MAP, SYMPTOM_CODE_MAP
from analysis.parsing import map_codes, parse_compact_codes, parse_region_codes
from analysis.rome_matcher import rome_map


def build_participant_rome_mapping(
    symptoms_df: pd.DataFrame,
    symptom_col: str = "Symptom",
    region_col: str = "Region",
    id_col: Optional[str] = None,
    symptom_code_map: Optional[Dict] = None,
    region_code_map: Optional[Dict] = None,
) -> pd.DataFrame:
    """
    Build participant-level Rome IV mapping from symptom/region codes.

    Parameters
    ----------
    symptoms_df : pd.DataFrame
        DataFrame with symptom and region code columns.
    symptom_col : str
        Column name for symptom codes.
    region_col : str
        Column name for region codes.
    id_col : str, optional
        Column name for participant ID. If None, uses index.
    symptom_code_map : dict, optional
        Symptom code to label mapping. Uses default if None.
    region_code_map : dict, optional
        Region code to label mapping. Uses default if None.

    Returns
    -------
    pd.DataFrame
        Participant-level mapping with columns: participant_id, symptoms,
        regions, rome_matches, top_disease, top_score.
    """
    if symptom_code_map is None:
        symptom_code_map = SYMPTOM_CODE_MAP
    if region_code_map is None:
        region_code_map = REGION_CODE_MAP

    results = []

    for idx, row in symptoms_df.iterrows():
        pid = row[id_col] if id_col else idx

        # Parse codes
        raw_symptoms = str(row.get(symptom_col, ""))
        raw_regions = str(row.get(region_col, ""))

        symptom_codes = parse_compact_codes(
            raw_symptoms, valid_codes=set(symptom_code_map.keys())
        )
        region_codes = parse_region_codes(
            raw_regions, valid_codes=set(region_code_map.keys())
        )

        # Map to labels
        symptom_labels = map_codes(symptom_codes, symptom_code_map)
        region_labels = map_codes(region_codes, region_code_map)

        # Run Rome IV matching
        matches = rome_map(symptom_labels, region_labels)

        top_disease = matches[0]["disease"] if matches else "No Match"
        top_score = matches[0]["score"] if matches else 0.0

        results.append(
            {
                "participant_id": pid,
                "symptoms": symptom_labels,
                "regions": region_labels,
                "rome_matches": matches,
                "top_disease": top_disease,
                "top_score": top_score,
            }
        )

    return pd.DataFrame(results)
