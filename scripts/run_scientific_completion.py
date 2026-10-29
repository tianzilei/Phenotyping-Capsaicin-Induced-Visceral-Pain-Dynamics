"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]


def matched(ss, rr, rule):
    required_all = rule.get("required_all", [])
    required_any = rule.get("required_any", [])
    regions = rule.get("required_region_any", [])
    if (
        not set(required_all) <= ss
        or (required_any and (not set(required_any) & ss))
        or (regions and (not set(regions) & rr))
    ):
        return False
    return bool(
        set(required_all) & ss
        or set(required_any) & ss
        or set(regions) & rr
        or set(rule.get("supportive", [])) & ss
        or set(rule.get("supportive_region_any", [])) & rr
    )
