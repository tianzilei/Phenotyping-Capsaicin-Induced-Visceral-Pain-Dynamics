"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
from capsaicin.data_locations import resolve_input

ROOT = Path(__file__).resolve().parents[1]


def resolve_external_path(value):
    p = resolve_input(value)
    return p if p.is_file() else None


def resolve_candidates(value):
    p = resolve_external_path(value)
    return [p] if p is not None else []
