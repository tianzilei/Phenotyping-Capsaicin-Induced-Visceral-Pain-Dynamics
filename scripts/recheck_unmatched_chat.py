"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from pathlib import Path
import re
from build_relaxed_enc_mapping import (
    normalize_name,
    source_identity_name,
    code,
    levenshtein,
)
from capsaicin.participant_matching import strip_group_suffix

ROOT = Path(__file__).resolve().parents[1]


def named_line(line, name):
    """Require an exact participant name immediately after its own numeric code."""
    match = re.search(
        "(?:^|[：:\\s])([Zz]?\\d{1,3})\\s*([\\u3400-\\u9fff·]{2,8})", line
    )
    if not match or strip_group_suffix(match.group(2)) != name:
        return None
    return code(match.group(1))


def can_correct(
    file, sid, subjects, mentions, accepted, canonical, owners, max_distance
):
    s = subjects[sid]
    name = normalize_name(source_identity_name(s))
    if (
        sum(
            (normalize_name(source_identity_name(x)) == name for x in subjects.values())
        )
        != 1
    ):
        return False
    number, abbr, date = (file["recording_code"], file["filename_abbr"], file["date"])
    if not number or abbr not in canonical[sid] or number == s["legacy_code_numeric"]:
        return False
    if levenshtein(number, s["legacy_code_numeric"]) > max_distance:
        return False
    if not any(
        (
            m["current_subject_id"] == sid
            and m["target_date"] == date
            and (m["mentioned_code"] == s["legacy_code_numeric"])
            for m in mentions
        )
    ):
        return False
    if not any(
        (
            r["current_subject_id"] == sid
            and r["date"] == date
            and (r["filename_abbr"] == abbr)
            for r in accepted
        )
    ):
        return False
    return all(
        (
            abbr not in canonical[owner]
            and normalize_name(source_identity_name(subjects[owner])) != name
            for owner in owners
        )
    )
