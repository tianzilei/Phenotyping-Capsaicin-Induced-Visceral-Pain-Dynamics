"""
Rome IV symptom-to-disease matching engine.
Scores participants against Rome IV diagnostic rules.
"""

from typing import Dict, List, Optional, Set, Tuple


def rome_match_score(
    symptom_set: Set[str],
    region_set: Set[str],
    rule: Dict,
) -> Tuple[float, List[str], List[str], List[str], List[str]]:
    """
    Score a single Rome IV rule against a participant's symptom+region set.

    Parameters
    ----------
    symptom_set : set of str
        Participant's symptom labels.
    region_set : set of str
        Participant's region labels.
    rule : dict
        Rome IV rule with keys: required_all, required_any, supportive,
        required_region_any, supportive_region_any.

    Returns
    -------
    tuple of (float, list, list, list, list)
        (score, matched_required, matched_supportive,
         matched_required_regions, matched_supportive_regions)
    """
    required_all = rule.get("required_all", [])
    required_any = rule.get("required_any", [])
    supportive = rule.get("supportive", [])
    required_region_any = rule.get("required_region_any", [])
    supportive_region_any = rule.get("supportive_region_any", [])

    # Check required_all: ALL must be present
    matched_required_all = [s for s in required_all if s in symptom_set]
    if len(matched_required_all) < len(required_all):
        return (0.0, [], [], [], [])

    # Check required_any: at least ONE must be present
    matched_required_any = [s for s in required_any if s in symptom_set]
    if not matched_required_any and required_any:
        return (0.0, [], [], [], [])

    # Check required_region_any: at least ONE must be present
    matched_required_regions = [r for r in required_region_any if r in region_set]
    if not matched_required_regions and required_region_any:
        return (0.0, [], [], [], [])

    # Compute score
    # Required symptoms contribute more weight
    required_weight = 2.0
    supportive_weight = 1.0

    score = 0.0
    score += len(matched_required_all) * required_weight
    score += len(matched_required_any) * required_weight
    score += len(matched_required_regions) * required_weight

    # Supportive symptoms/regions (bonus)
    matched_supportive = [s for s in supportive if s in symptom_set]
    matched_supportive_regions = [r for r in supportive_region_any if r in region_set]

    score += len(matched_supportive) * supportive_weight
    score += len(matched_supportive_regions) * supportive_weight

    return (
        score,
        matched_required_all + matched_required_any,
        matched_supportive,
        matched_required_regions,
        matched_supportive_regions,
    )


def rome_map(
    symptoms: List[str],
    regions: List[str],
    rules: Optional[Dict] = None,
) -> List[Dict]:
    """
    Map symptoms and regions to Rome IV disease categories.

    Parameters
    ----------
    symptoms : list of str
        Participant's symptom labels.
    regions : list of str
        Participant's region labels.
    rules : dict, optional
        Rome IV rules dictionary. Uses default if None.

    Returns
    -------
    list of dict
        Sorted list of matching disease dictionaries, each containing:
        - disease: str
        - score: float
        - matched_required: list
        - matched_supportive: list
        - matched_required_regions: list
        - matched_supportive_regions: list
    """
    if rules is None:
        from analysis.rome_rules import ROME_RULES

        rules = ROME_RULES

    symptom_set = set(symptoms)
    region_set = set(regions)

    results = []

    for disease_name, rule in rules.items():
        score, matched_req, matched_sup, matched_req_reg, matched_sup_reg = (
            rome_match_score(symptom_set, region_set, rule)
        )

        if score > 0:
            results.append(
                {
                    "disease": disease_name,
                    "score": score,
                    "matched_required": matched_req,
                    "matched_supportive": matched_sup,
                    "matched_required_regions": matched_req_reg,
                    "matched_supportive_regions": matched_sup_reg,
                }
            )

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)

    return results
