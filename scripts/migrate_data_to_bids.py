"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def js(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(p.suffix + ".tmp")
    temp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temp.replace(p)


def read(p):
    with Path(p).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(p, rows, delimiter=","):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=delimiter)
        w.writeheader()
        w.writerows(rows)


def subject_label(s):
    if not s.startswith("SUBJECT") or not s[7:].isdigit():
        raise ValueError("Unexpected research ID")
    return "sub-" + s[7:]


def behavior_rows(row):
    result = []
    for minute in range(1, 21):
        original = row.get(f"VAS_{minute}min", "")
        token = original.strip()
        if token in ("E", "T"):
            rating = "n/a"
            status = token
        elif token in ("", "NA", "N/A", "NaN"):
            rating = "n/a"
            status = "missing"
        else:
            value = float(token)
            if not 0 <= value <= 10:
                raise ValueError("VAS out of range")
            rating = token
            status = "observed"
        result.append(
            dict(
                time_min=minute,
                vas=rating,
                original_token=original or "n/a",
                observation_status=status,
            )
        )
    return result
