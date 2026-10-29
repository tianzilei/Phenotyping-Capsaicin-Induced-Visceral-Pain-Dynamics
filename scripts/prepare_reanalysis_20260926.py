"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(p):
    with Path(p).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(p, rows, fields=None):
    fields = fields or list(dict.fromkeys((k for r in rows for k in r)))
    with Path(p).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def dump(p, obj):
    Path(p).write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
