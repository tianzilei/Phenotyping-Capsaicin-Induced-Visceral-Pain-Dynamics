"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import re
from build_relaxed_enc_mapping import ELECTRO, code

ROOT = Path(__file__).resolve().parents[1]


def parse_extended(name: str) -> dict[str, str] | None:
    if name.startswith("._"):
        return None
    stem = Path(name).stem
    stem = re.sub("acq$", "", stem, flags=re.I)
    token = stem.split("_")[0]
    match = re.fullmatch("(20\\d{6})(\\d{1,3})?([A-Za-z]*)", token)
    if not match:
        return None
    date, numeric, letters = match.groups()
    try:
        datetime.strptime(date, "%Y%m%d")
    except ValueError:
        return None
    letters = letters.upper()
    if len(letters) == 1 and letters in ALL_STAGES:
        abbr, stage = ("", letters)
    elif len(letters) >= 5 and re.fullmatch("[A-Z]{4}(?:[NCE]+|P)", letters):
        abbr, stage = (letters[:4], letters[-1])
    elif len(letters) == 4 and letters[-1] in ALL_STAGES:
        abbr, stage = (letters[:3], letters[-1])
        return {
            "date": date,
            "recording_code": code(numeric),
            "filename_abbr": abbr,
            "stage": stage,
            "parse_rule": "three_letter_abbreviation_requires_anchor",
        }
    elif len(letters) == 4:
        abbr, stage = (letters, "")
    else:
        return None
    rule = "explicit_phase"
    if not numeric:
        rule = "missing_code_requires_date_abbreviation_anchor"
    elif not abbr:
        rule = "missing_abbreviation_requires_date_code_anchor"
    return {
        "date": date,
        "recording_code": code(numeric),
        "filename_abbr": abbr,
        "stage": stage,
        "parse_rule": rule,
    }


def components(rows, rest_stages=("N", "C")):
    return {
        "electrophysiology_E": any(
            (r["modality"] in ELECTRO and r["stage"] == "E" for r in rows)
        ),
        "electrophysiology_pre_rest": any(
            (r["modality"] in ELECTRO and r["stage"] in set(rest_stages) for r in rows)
        ),
        "fnirs_E": any((r["modality"] == "fnirs" and r["stage"] == "E" for r in rows)),
        "fnirs_pre_rest": any(
            (r["modality"] == "fnirs" and r["stage"] in set(rest_stages) for r in rows)
        ),
    }


def unique_identity(sids, identities):
    return bool(sids) and len({identities[s] for s in sids}) == 1


def unphased_known_alias(file, alias_owners, short_stages):
    """An abbreviation ending in N/E is ambiguous unless paired stages exist."""
    if file.get("parse_rule") != "three_letter_abbreviation_requires_anchor":
        return False
    stages = short_stages.get(
        (file["date"], file["recording_code"], file["filename_abbr"]), set()
    )
    complementary = "E" in stages and bool(stages & {"N", "C"})
    return file["filename_abbr"] + file["stage"] in alias_owners and (not complementary)


def resolve_claims(claims, identities, existing_owners):
    """Resolve independently per file; scores are rule priorities, not probabilities."""
    accepted, review = ([], [])
    grouped = defaultdict(list)
    for row in claims:
        grouped[row["path"]].append(row)
    for path, rows in grouped.items():
        best = max((r["priority"] for r in rows))
        top = {r["current_subject_id"] for r in rows if r["priority"] == best}
        fixed = existing_owners.get(path, set())
        allowed = top | fixed
        safe = unique_identity(allowed, identities)
        for row in rows:
            same_identity = (
                safe
                and identities[row["current_subject_id"]] == identities[next(iter(top))]
            )
            if same_identity and row["supported"]:
                accepted.append(row)
            else:
                review.append(
                    {
                        **row,
                        "review_reason": "identity_conflict"
                        if not same_identity
                        else "abbreviation_only_or_visit_unverified",
                    }
                )
    return (accepted, review)


ALL_STAGES = {"E", "N", "C", "P"}
ALL_STAGES = {"E", "N", "C", "P"}
