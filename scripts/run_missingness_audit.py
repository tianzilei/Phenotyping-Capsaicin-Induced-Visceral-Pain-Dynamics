"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(p):
    with p.open(encoding="utf-8", newline="") as h:
        return list(csv.DictReader(h))


def write(p, rows):
    with p.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
