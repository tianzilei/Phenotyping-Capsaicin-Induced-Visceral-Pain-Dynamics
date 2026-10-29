"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def describe(x):
    return dict(
        n=len(x),
        minimum=min(x) if x else None,
        median=statistics.median(x) if x else None,
        maximum=max(x) if x else None,
    )
