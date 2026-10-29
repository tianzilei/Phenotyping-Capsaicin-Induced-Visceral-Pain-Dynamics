"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
import re
from build_relaxed_enc_mapping import levenshtein, code

ROOT = Path(__file__).resolve().parents[1]


def parse_reverse(name):
    """Parse explicit phase syntax; ambiguous names require identity evidence."""
    if name.startswith("._"):
        return None
    stem = Path(name).stem
    stem = re.sub("acq$", "", stem, flags=re.I)
    token = stem.split("_")[0]
    match = re.fullmatch("(20\\d{6})(\\d{1,3})?([A-Za-z]{3,4}?)([ENC]|NE)", token, re.I)
    if not match:
        match = re.fullmatch("(20\\d{6})(\\d{1,3})([ENC])", token, re.I)
        if not match:
            return None
        date, number, phase = match.groups()
        abbr = ""
    else:
        date, number, abbr, phase = match.groups()
    try:
        datetime.strptime(date, "%Y%m%d")
    except ValueError:
        return None
    return {
        "date": date,
        "recording_code": code(number),
        "filename_abbr": abbr.upper(),
        "stage": phase[-1].upper(),
        "raw_participant_prefix": token[: -len(phase)].upper(),
        "parse_status": "short_abbreviation_ambiguous"
        if len(abbr) == 3
        else "explicit_phase",
    }


def log_support(file, subject, aliases, logs, anchors, max_distance=1):
    """Require actual log metadata; dates from filenames alone are insufficient."""
    sid = subject["current_subject_id"]
    for log in logs:
        if not log["participant"] or not log["actual_date"]:
            continue
        exact_prefix = log["participant"] == file["raw_participant_prefix"]
        short_variant = (
            file["parse_status"] == "short_abbreviation_ambiguous"
            and log["recording_code"]
            == subject["legacy_code_numeric"]
            == file["recording_code"]
            and (log["actual_date"] == file["date"])
            and (log["abbreviation"] in aliases)
            and (
                levenshtein(log["abbreviation"], file["filename_abbr"]) <= max_distance
            )
        )
        if short_variant:
            return ("source_code_date_log_corroborates_short_abbreviation", log)
        if exact_prefix and file["filename_abbr"] in aliases:
            if (log["actual_date"], file["filename_abbr"]) in anchors:
                return (
                    "exact_log_participant_actual_date_and_existing_identity_anchor",
                    log,
                )
            if (
                log["recording_code"] == subject["legacy_code_numeric"]
                and log["abbreviation"] in aliases
            ):
                return ("exact_log_participant_source_code_abbreviation", log)
    return ("", None)
