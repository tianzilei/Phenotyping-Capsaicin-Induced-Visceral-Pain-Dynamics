"""Resolve exact source aliases through the verified local D: copy index."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.data_locations import (
    resolve_input,
    execution_config,
    relocation_evidence,
)


def resolve_external_path(value):
    p = resolve_input(value)
    return p if p.is_file() else None


def resolve_candidates(value):
    p = resolve_external_path(value)
    return [p] if p is not None else []
