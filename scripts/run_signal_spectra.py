"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_rows(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys((k for row in rows for k in row)))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
