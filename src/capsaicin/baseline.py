"""Prepare an analysis copy of baseline questionnaire data.

The source CSV is never modified. Conditional non-applicability is encoded
explicitly so that it cannot be confused with an unreported value.
"""

from __future__ import annotations

import csv
from pathlib import Path


class BaselinePreparationError(ValueError):
    """Raised when the conditional intake fields are internally inconsistent."""


TIME_FIELD = "Time_since_last_intake_h"
RECENT_FIELD = "Recent_spicy_intake_24h"
STATUS_FIELD = "Time_since_last_intake_h_status"


def _recent_intake(token: str) -> int:
    value = token.strip()
    if value in {"0", "0.0"}:
        return 0
    if value in {"1", "1.0"}:
        return 1
    raise BaselinePreparationError(f"{RECENT_FIELD} must be coded 0/1; found {token!r}")


def prepare_baseline_rows(
    source: Path,
) -> tuple[list[str], list[dict[str, str]], dict[str, int]]:
    """Read *source* and return rows with explicit conditional NA coding."""
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    required = {"ID", RECENT_FIELD, TIME_FIELD}
    missing = sorted(required - set(fields))
    if missing:
        raise BaselinePreparationError(f"missing required columns: {missing}")
    if STATUS_FIELD in fields:
        raise BaselinePreparationError(f"source already contains {STATUS_FIELD}")

    counts = {
        "rows": len(rows),
        "filled_na_not_applicable": 0,
        "reported_hours": 0,
    }
    seen_ids: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        subject_id = (row.get("ID") or "").strip()
        if not subject_id or subject_id in seen_ids:
            raise BaselinePreparationError(
                f"empty or duplicate ID at CSV line {line_number}"
            )
        seen_ids.add(subject_id)

        recent = _recent_intake(row.get(RECENT_FIELD) or "")
        elapsed = (row.get(TIME_FIELD) or "").strip()
        if recent == 0:
            if elapsed and elapsed.upper() not in {"NA", "N/A"}:
                raise BaselinePreparationError(
                    f"{TIME_FIELD} must be NA when {RECENT_FIELD}=0 "
                    f"(CSV line {line_number})"
                )
            row[TIME_FIELD] = "NA"
            row[STATUS_FIELD] = "not_applicable_no_recent_intake"
            counts["filled_na_not_applicable"] += 1
        else:
            if not elapsed or elapsed.upper() in {"NA", "N/A"}:
                raise BaselinePreparationError(
                    f"{TIME_FIELD} is required when {RECENT_FIELD}=1 "
                    f"(CSV line {line_number})"
                )
            try:
                hours = float(elapsed)
            except ValueError as exc:
                raise BaselinePreparationError(
                    f"invalid {TIME_FIELD} at CSV line {line_number}: {elapsed!r}"
                ) from exc
            if not 0 < hours <= 24:
                raise BaselinePreparationError(
                    f"{TIME_FIELD} must be in (0, 24] at CSV line {line_number}"
                )
            row[TIME_FIELD] = elapsed
            row[STATUS_FIELD] = "reported_hours"
            counts["reported_hours"] += 1

    return fields + [STATUS_FIELD], rows, counts


def write_baseline_copy(source: Path, destination: Path) -> dict[str, int]:
    """Write a new analysis CSV, refusing to overwrite an existing file."""
    if destination.exists():
        raise BaselinePreparationError(f"output already exists: {destination}")
    fields, rows, counts = prepare_baseline_rows(source)
    destination.parent.mkdir(parents=True, exist_ok=False)
    with destination.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return counts
