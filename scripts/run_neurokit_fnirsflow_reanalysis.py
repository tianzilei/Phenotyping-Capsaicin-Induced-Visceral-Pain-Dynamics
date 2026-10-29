"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path: Path, data):
    data = list(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys((k for r in data for k in r)))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(data)
