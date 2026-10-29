"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def numeric_summary(rows, field):
    values = [
        float(row[field])
        for row in rows
        if row.get(field) not in (None, "") and math.isfinite(float(row[field]))
    ]
    return (
        {
            "minimum": min(values),
            "median": statistics.median(values),
            "maximum": max(values),
        }
        if values
        else None
    )
