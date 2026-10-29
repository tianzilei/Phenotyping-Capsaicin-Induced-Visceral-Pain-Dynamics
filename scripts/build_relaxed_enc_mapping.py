"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
import re
from pathlib import Path
from capsaicin.participant_matching import levenshtein, normalize_name

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            return list(csv.DictReader(raw.decode(encoding).splitlines()))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {path}")


def write_csv(
    path: Path, rows: list[dict[str, object]], fields: list[str] | None = None
) -> None:
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def code(value: object) -> str:
    match = re.search("\\d+", str(value or ""))
    return str(int(match.group())) if match else ""


def split_tokens(value: object) -> list[str]:
    return sorted(
        {
            token.strip().upper()
            for token in re.split("[;\\s]+", str(value or ""))
            if token.strip()
        }
    )


def vas_signature(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        (
            str(row.get(f"VAS_{minute}min", "")).strip().upper()
            for minute in range(1, 21)
        )
    )


def source_identity_name(subject: dict[str, str]) -> str:
    """Return the name attached to the verified source-workbook VAS row.

    ``bridge_name`` comes from a later legacy integration table.  It is useful
    corroboration only when it agrees with the workbook identity; several rows
    have demonstrably shifted names despite retaining the source VAS values.
    """
    return str(subject.get("xlsx_name") or subject.get("bridge_name") or "").strip()


def reviewed_mapping_resolution(
    subject: dict[str, str], map_abbr: str, source_name_abbrs: set[str]
) -> tuple[str, str, int]:
    """Classify a reviewed filename stem linked to a verified XLSX/VAS row."""
    map_abbr = str(map_abbr or "").upper()
    source_name = normalize_name(source_identity_name(subject))
    bridge_name = normalize_name(subject.get("bridge_name", ""))
    if source_name and bridge_name and (source_name != bridge_name):
        return (
            "source_workbook_code_vas_identity_overrides_stale_legacy_name",
            "high",
            98,
        )
    if map_abbr in source_name_abbrs:
        return ("same_source_identity_and_abbreviation", "high", 98)
    if (
        source_name_abbrs
        and min((levenshtein(map_abbr, abbr) for abbr in source_name_abbrs)) == 1
    ):
        return (
            "same_source_identity_reviewed_one_character_abbreviation_variant",
            "medium",
            85,
        )
    return ("same_source_identity_reviewed_abbreviation_variant", "medium", 80)


def add_evidence(
    target: list[dict[str, object]],
    subject: dict[str, str],
    recording_code: str,
    abbr: str,
    basis: str,
    tier: str,
    score: int,
    source: str,
) -> None:
    recording_code, abbr = (code(recording_code), str(abbr or "").strip().upper())
    if not recording_code or not re.fullmatch("[A-Z]{4}", abbr):
        return
    target.append(
        {
            "current_subject_id": subject["current_subject_id"],
            "subject_name": source_identity_name(subject),
            "source_workbook_name": source_identity_name(subject),
            "legacy_bridge_name": subject.get("bridge_name", ""),
            "legacy_code_numeric": subject["legacy_code_numeric"],
            "recording_code": recording_code,
            "filename_abbr": abbr,
            "evidence_basis": basis,
            "evidence_tier": tier,
            "evidence_score": score,
            "evidence_source": source,
        }
    )


ELECTRO = {
    "electrophysiology",
    "electrophysiology_multichannel",
    "electrophysiology_ecg",
    "electrophysiology_egg",
    "electrophysiology_emg",
}
