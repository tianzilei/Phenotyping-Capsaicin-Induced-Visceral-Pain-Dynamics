"""Eligibility rules for the experimental resting reference state."""

from __future__ import annotations

REST_PRIORITY = ("N", "C", "P")


def is_rest_reference_eligible(row) -> bool:
    """Admit N/C strict mappings and reviewed P rest supplements."""
    stage = str(row.get("stage", "")).upper()
    if stage in {"N", "C"}:
        return row.get("match_status") == "accepted_strict"
    if stage == "P":
        return (
            str(row.get("supported", "")).lower() == "true"
            and row.get("rule_version") == "enc_matching_v3"
            and row.get("parse_rule") == "explicit_phase"
        )
    return False


def choose_rest_stage(stages, priority=REST_PRIORITY):
    """Choose one existing stage without relabelling or concatenating records."""
    available = set(stages)
    return next((stage for stage in priority if stage in available), None)
