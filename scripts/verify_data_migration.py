"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path, delimiter=","):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=delimiter))
