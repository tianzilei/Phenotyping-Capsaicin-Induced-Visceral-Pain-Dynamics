"""Resolve E/N/C recording identifiers with an auditable evidence hierarchy.

This supplements, rather than overwrites, the strict code+abbreviation inventory.
Only E (capsaicin trial) and N/C (pre-capsaicin rest) are eligible.  A/P/T and
all other phases remain excluded.  Participant files are referenced in place.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from capsaicin.participant_matching import levenshtein, normalize_name  # noqa: E402


ELECTRO = {
    "electrophysiology",
    "electrophysiology_multichannel",
    "electrophysiology_ecg",
    "electrophysiology_egg",
    "electrophysiology_emg",
}


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


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def code(value: object) -> str:
    match = re.search(r"\d+", str(value or ""))
    return str(int(match.group())) if match else ""


def split_tokens(value: object) -> list[str]:
    return sorted(
        {
            token.strip().upper()
            for token in re.split(r"[;\s]+", str(value or ""))
            if token.strip()
        }
    )


def vas_signature(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        str(row.get(f"VAS_{minute}min", "")).strip().upper() for minute in range(1, 21)
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
    if source_name and bridge_name and source_name != bridge_name:
        return (
            "source_workbook_code_vas_identity_overrides_stale_legacy_name",
            "high",
            98,
        )
    if map_abbr in source_name_abbrs:
        return "same_source_identity_and_abbreviation", "high", 98
    if (
        source_name_abbrs
        and min(levenshtein(map_abbr, abbr) for abbr in source_name_abbrs) == 1
    ):
        return (
            "same_source_identity_reviewed_one_character_abbreviation_variant",
            "medium",
            85,
        )
    return "same_source_identity_reviewed_abbreviation_variant", "medium", 80


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
    recording_code, abbr = code(recording_code), str(abbr or "").strip().upper()
    if not recording_code or not re.fullmatch(r"[A-Z]{4}", abbr):
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


def main() -> int:
    merged_dir = sorted(
        (ROOT / "02_quality_control").glob("capsaicin_baseline_merged_*"),
        key=lambda p: p.stat().st_mtime,
    )[-1]
    merged_path = merged_dir / "capsaicin_baseline_merged_private.csv"
    subjects = read_csv(merged_path)
    if len(subjects) != 216:
        raise ValueError(f"Expected 216 included rows, got {len(subjects)}")

    strict_dir = sorted(
        (ROOT / "02_quality_control").glob("enc_signal_inventory_*"),
        key=lambda p: p.stat().st_mtime,
    )[-1]
    strict_files_path = strict_dir / "reverse_files_to_subject_private.csv"
    strict_mapping_path = strict_dir / "selected_enc_mapping_private.csv"
    files = read_csv(strict_files_path)
    selected_mapping = read_csv(strict_mapping_path)
    files_by_pair: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in files:
        if row.get("stage") in {"E", "N", "C"}:
            files_by_pair[
                (code(row.get("recording_code")), row.get("filename_abbr", "").upper())
            ].append(row)

    old_root = next(
        Path("D:/") / name
        for name in os.listdir("D:/")
        if name.startswith("capsaicin") and "analysis" not in name
    )
    old_subject_path = old_root / "data" / "subject_baseline_info.csv"
    old_subjects = read_csv(old_subject_path)
    old_by_code = {
        code(row.get("ID")): row for row in old_subjects if code(row.get("ID"))
    }
    old_by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in old_subjects:
        old_by_name[normalize_name(row.get("Name", ""))].append(row)

    chat_dir = sorted(
        (ROOT / "02_quality_control").glob("chat_participant_signal_audit_*"),
        key=lambda p: p.stat().st_mtime,
    )[-1]
    chat_path = chat_dir / "forward_chat_to_raw_private.csv"
    chat_rows = read_csv(chat_path)
    subjects_by_sid = {row["current_subject_id"]: row for row in subjects}
    subjects_by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    for subject in subjects:
        subjects_by_name[normalize_name(source_identity_name(subject))].append(subject)

    # A legacy abbreviation is identity evidence only when its legacy name is
    # the same as the source-workbook name.  Numeric-row agreement alone is
    # insufficient because names in the later integration table shifted for
    # 37 otherwise VAS-identical rows.
    evidence: list[dict[str, object]] = []
    for subject in subjects:
        current_code = subject["legacy_code_numeric"]
        known = old_by_code.get(current_code, {})
        if normalize_name(known.get("Name", "")) == normalize_name(
            source_identity_name(subject)
        ):
            add_evidence(
                evidence,
                subject,
                current_code,
                known.get("name_abbr", ""),
                "current_code_source_name_and_legacy_abbreviation",
                "strict",
                100,
                str(old_subject_path),
            )

        # An exact Chinese-name history resolves numbering drift.  The numeric
        # code and abbreviation must originate from the same legacy row, and
        # repeated names are linked only when the VAS signature also agrees.
        for old in old_by_name.get(normalize_name(source_identity_name(subject)), []):
            if vas_signature(old) != vas_signature(subject):
                continue
            add_evidence(
                evidence,
                subject,
                old.get("ID", ""),
                old.get("name_abbr", ""),
                "exact_source_name_historical_code_and_abbreviation",
                "high",
                90,
                str(old_subject_path),
            )

    # The reviewed fNIRS table establishes an exact stem for the workbook code.
    # The current row is already connected to that workbook row by exact VAS,
    # so a stale name in the later legacy integration table must not redirect
    # the stem to another current record merely because its abbreviation fits.
    mapping_reassignment_audit = []
    for mapping in selected_mapping:
        mapped_subject = subjects_by_sid.get(mapping.get("current_subject_id", ""))
        map_abbr = str(mapping.get("map_name_abbr", "")).upper()
        known_abbr = str(mapping.get("known_name_abbr", "")).upper()
        resolved_owners: list[dict[str, str]] = []
        resolution, tier, score = "unresolved_mapping_without_verified_subject", "", 0
        if mapped_subject and code(
            mapping.get("map_recording_code")
        ) == mapped_subject.get("legacy_code_numeric"):
            resolved_owners = [mapped_subject]
            source_abbrs = {
                str(row.get("name_abbr", "")).upper()
                for row in old_by_name.get(
                    normalize_name(source_identity_name(mapped_subject)), []
                )
                if re.fullmatch(r"[A-Z]{4}", str(row.get("name_abbr", "")).upper())
            }
            resolution, tier, score = reviewed_mapping_resolution(
                mapped_subject, map_abbr, source_abbrs
            )
        for subject in resolved_owners:
            add_evidence(
                evidence,
                subject,
                mapping.get("map_recording_code", ""),
                map_abbr,
                resolution,
                tier,
                score,
                str(strict_mapping_path),
            )
        mapping_reassignment_audit.append(
            {
                "mapping_subject_id": mapping.get("current_subject_id", ""),
                "mapping_subject_name": mapping.get("subject_name", ""),
                "mapping_recording_code": mapping.get("map_recording_code", ""),
                "known_name_abbr": known_abbr,
                "map_name_abbr": map_abbr,
                "source_workbook_name": source_identity_name(mapped_subject)
                if mapped_subject
                else "",
                "legacy_bridge_name": mapped_subject.get("bridge_name", "")
                if mapped_subject
                else "",
                "stage": mapping.get("stage", ""),
                "resolution": resolution,
                "resolved_subject_ids": ";".join(
                    sorted({row["current_subject_id"] for row in resolved_owners})
                ),
                "resolved_subject_names": ";".join(
                    sorted({source_identity_name(row) for row in resolved_owners})
                ),
            }
        )

    # Chat exact-name rows add historical visit codes.  The filename
    # abbreviation is accepted only when the chat audit observed it on files
    # linked to that exact name/date/code row.
    for chat in chat_rows:
        chat_name = normalize_name(chat.get("chat_name", ""))
        if (
            chat.get("confidence") != "high"
            or chat.get("name_match_status") != "exact_name"
        ):
            continue
        for subject in subjects_by_name.get(chat_name, []):
            for abbr in split_tokens(chat.get("filename_abbreviations", "")):
                add_evidence(
                    evidence,
                    subject,
                    chat.get("code_numeric", ""),
                    abbr,
                    "chat_exact_name_date_code_and_observed_abbreviation",
                    "medium",
                    80,
                    str(chat_path),
                )

    # One-character name variants require the independent VAS bridge to point
    # to exactly one included row plus abbreviation support in the chat audit.
    for chat in chat_rows:
        candidates = split_tokens(chat.get("current_subject_candidates_vas", ""))
        if (
            chat.get("confidence") != "high"
            or chat.get("name_match_status") != "one_character_variant"
            or len(candidates) != 1
            or chat.get("abbreviation_consistent") != "True"
        ):
            continue
        subject = subjects_by_sid.get(candidates[0])
        if not subject:
            continue
        for abbr in split_tokens(chat.get("filename_abbreviations", "")):
            add_evidence(
                evidence,
                subject,
                chat.get("code_numeric", ""),
                abbr,
                "one_character_name_variant_plus_unique_vas_bridge_and_abbreviation",
                "medium",
                75,
                str(chat_path),
            )

    # Collapse repeated evidence while retaining all bases and sources.
    grouped_evidence: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(
        list
    )
    for row in evidence:
        grouped_evidence[
            (
                str(row["current_subject_id"]),
                str(row["recording_code"]),
                str(row["filename_abbr"]),
            )
        ].append(row)
    collapsed = []
    for key, rows in grouped_evidence.items():
        best = max(rows, key=lambda row: int(row["evidence_score"]))
        collapsed.append(
            {
                **best,
                "evidence_bases": ";".join(
                    sorted({str(row["evidence_basis"]) for row in rows})
                ),
                "evidence_sources": ";".join(
                    sorted({str(row["evidence_source"]) for row in rows})
                ),
                "independent_evidence_count": len(
                    {str(row["evidence_basis"]) for row in rows}
                ),
            }
        )

    # Resolve an acquisition pair to its strongest owner.  A subject whose
    # current included code equals the recording code outranks a same-name
    # historical-code candidate.  Tied top owners may share only when both the
    # exact name and VAS signature agree.
    identity_key = {
        row["current_subject_id"]: (
            normalize_name(source_identity_name(row)),
            vas_signature(row),
        )
        for row in subjects
    }
    evidence_by_pair: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in collapsed:
        evidence_by_pair[
            (str(row["recording_code"]), str(row["filename_abbr"]))
        ].append(row)
    accepted_owner_sids: dict[tuple[str, str], set[str]] = {}
    pair_owners: dict[tuple[str, str], set[tuple[str, tuple[str, ...]]]] = {}
    for pair, rows in evidence_by_pair.items():
        top_score = max(int(row["evidence_score"]) for row in rows)
        top_rows = [row for row in rows if int(row["evidence_score"]) == top_score]
        top_identities = {
            identity_key[str(row["current_subject_id"])] for row in top_rows
        }
        pair_owners[pair] = top_identities
        if len(top_identities) == 1:
            accepted = {str(row["current_subject_id"]) for row in top_rows}
            # Lower-ranked records may reference the same acquisition only if
            # they are demonstrably the same name-plus-VAS identity.
            sole_identity = next(iter(top_identities))
            accepted.update(
                str(row["current_subject_id"])
                for row in rows
                if identity_key[str(row["current_subject_id"])] == sole_identity
            )
            accepted_owner_sids[pair] = accepted
        else:
            accepted_owner_sids[pair] = set()

    links = []
    conflicts = []
    for row in collapsed:
        pair = (str(row["recording_code"]), str(row["filename_abbr"]))
        ambiguous = not accepted_owner_sids[pair]
        matching_files = files_by_pair.get(pair, [])
        if ambiguous or str(row["current_subject_id"]) not in accepted_owner_sids[pair]:
            conflicts.append(
                {
                    **row,
                    "conflict_reason": (
                        "code_abbreviation_pair_has_tied_top_distinct_identities"
                        if ambiguous
                        else "lower_ranked_identity_evidence_rejected"
                    ),
                    "candidate_file_count": len(matching_files),
                }
            )
            continue
        for file in matching_files:
            links.append(
                {
                    **row,
                    **file,
                    "match_status": "accepted_relaxed"
                    if row["evidence_tier"] != "strict"
                    else "accepted_strict",
                    "shared_source_recording": len(accepted_owner_sids[pair]) > 1,
                    "independence_status": "recording_may_be_shared_across_duplicate_study_rows"
                    if len(accepted_owner_sids[pair]) > 1
                    else "one_resolved_owner",
                }
            )

    # Keep the strongest evidence if several paths reach the same subject/file.
    best_links: dict[tuple[str, str], dict[str, object]] = {}
    for row in links:
        key = (str(row["current_subject_id"]), str(row["path"]))
        current = best_links.get(key)
        if current is None or int(row["evidence_score"]) > int(
            current["evidence_score"]
        ):
            best_links[key] = row
    links = sorted(
        best_links.values(),
        key=lambda row: (
            str(row["current_subject_id"]),
            str(row["stage"]),
            str(row["path"]),
        ),
    )

    # Cross-device session reconciliation: once date+recording-code has one
    # resolved identity, include E/N/C files from the same acquisition session
    # even if one device used a misspelled abbreviation.  Conflicting session
    # owners are never expanded.
    session_seed: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in links:
        session_seed[(str(row["date"]), str(row["recording_code"]))].append(row)
    files_by_session: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for file in files:
        files_by_session[(str(file["date"]), code(file["recording_code"]))].append(file)
    session_conflicts = []
    expanded_links = list(links)
    for session, seeds in session_seed.items():
        seed_sids = sorted({str(row["current_subject_id"]) for row in seeds})
        session_identities = {identity_key[sid] for sid in seed_sids}
        if len(session_identities) != 1:
            session_conflicts.append(
                {
                    "date": session[0],
                    "recording_code": session[1],
                    "candidate_subject_ids": ";".join(seed_sids),
                    "candidate_subject_names": ";".join(
                        sorted(
                            {
                                source_identity_name(subjects_by_sid[sid])
                                for sid in seed_sids
                            }
                        )
                    ),
                    "conflict_reason": "date_code_session_has_multiple_distinct_identities",
                }
            )
            continue
        for sid in seed_sids:
            seed = max(
                (row for row in seeds if str(row["current_subject_id"]) == sid),
                key=lambda row: int(row["evidence_score"]),
            )
            for file in files_by_session.get(session, []):
                expanded_links.append(
                    {
                        **seed,
                        **file,
                        "evidence_basis": "unique_resolved_date_code_cross_device_session",
                        "evidence_bases": str(seed["evidence_bases"])
                        + ";unique_resolved_date_code_cross_device_session",
                        "evidence_tier": "medium",
                        "evidence_score": 70,
                        "match_status": "accepted_relaxed_session_expansion",
                        "independence_status": seed["independence_status"],
                    }
                )
    best_links = {}
    for row in expanded_links:
        key = (str(row["current_subject_id"]), str(row["path"]))
        current = best_links.get(key)
        if current is None or int(row["evidence_score"]) > int(
            current["evidence_score"]
        ):
            best_links[key] = row
    links = sorted(
        best_links.values(),
        key=lambda row: (
            str(row["current_subject_id"]),
            str(row["stage"]),
            str(row["path"]),
        ),
    )

    links_by_sid: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in links:
        links_by_sid[str(row["current_subject_id"])].append(row)
    coverage = []
    for subject in subjects:
        sid = subject["current_subject_id"]
        rows = links_by_sid[sid]
        electro_e = any(
            row.get("modality") in ELECTRO and row.get("stage") == "E" for row in rows
        )
        electro_rest = any(
            row.get("modality") in ELECTRO and row.get("stage") in {"N", "C"}
            for row in rows
        )
        fnirs_e = any(
            row.get("modality") == "fnirs" and row.get("stage") == "E" for row in rows
        )
        fnirs_rest = any(
            row.get("modality") == "fnirs" and row.get("stage") in {"N", "C"}
            for row in rows
        )
        tiers = {str(row["evidence_tier"]) for row in rows}
        coverage.append(
            {
                "current_subject_id": sid,
                "legacy_code_numeric": subject["legacy_code_numeric"],
                "subject_name": source_identity_name(subject),
                "legacy_bridge_name": subject.get("bridge_name", ""),
                "electrophysiology_E": electro_e,
                "electrophysiology_pre_rest": electro_rest,
                "electrophysiology_E_and_pre_rest": electro_e and electro_rest,
                "fnirs_E": fnirs_e,
                "fnirs_pre_rest": fnirs_rest,
                "fnirs_E_and_pre_rest": fnirs_e and fnirs_rest,
                "multimodal_E_and_pre_rest_complete": electro_e
                and electro_rest
                and fnirs_e
                and fnirs_rest,
                "uses_relaxed_evidence": bool(tiers - {"strict"}),
                "evidence_tiers": ";".join(sorted(tiers)),
                "linked_file_count": len(rows),
                "distinct_recording_codes": ";".join(
                    sorted({str(row["recording_code"]) for row in rows}, key=int)
                ),
            }
        )

    # Reassign legacy hash sources to the identity graph; never trust the
    # misleading SUBJECT filename itself.
    provenance_path = strict_dir / "derived_signal_hash_provenance_private.csv"
    provenance = read_csv(provenance_path)
    owners_by_pair: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in collapsed:
        pair = (str(row["recording_code"]), str(row["filename_abbr"]))
        if str(row["current_subject_id"]) in accepted_owner_sids.get(pair, set()):
            owners_by_pair[pair].append(row)
    reassigned = []
    for row in provenance:
        if not row.get("current_subject_id"):
            continue
        pair = (code(row.get("recording_code")), row.get("filename_abbr", "").upper())
        owners = owners_by_pair.get(pair, [])
        owner_sids = sorted({str(owner["current_subject_id"]) for owner in owners})
        owner_names = sorted({str(owner["subject_name"]) for owner in owners})
        named_sid = row.get("current_subject_id", "")
        reassigned.append(
            {
                **row,
                "resolved_subject_ids": ";".join(owner_sids),
                "resolved_subject_names": ";".join(owner_names),
                "relaxed_resolution_status": (
                    "filename_identity_confirmed"
                    if named_sid in owner_sids
                    else "reassigned_by_source_code_abbreviation"
                    if owner_sids
                    else "unresolved_no_unique_identity_owner"
                ),
                "do_not_use_under_current_filename": bool(
                    owner_sids and named_sid not in owner_sids
                ),
            }
        )

    out = (
        ROOT
        / "02_quality_control"
        / f"relaxed_enc_mapping_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    out.mkdir(parents=True)
    write_csv(out / "identity_evidence_private.csv", collapsed)
    write_csv(
        out / "reviewed_mapping_reassignment_private.csv", mapping_reassignment_audit
    )
    write_csv(out / "accepted_subject_to_files_private.csv", links)
    write_csv(out / "unresolved_identity_conflicts_private.csv", conflicts)
    write_csv(
        out / "unresolved_session_conflicts_private.csv",
        session_conflicts,
        [
            "date",
            "recording_code",
            "candidate_subject_ids",
            "candidate_subject_names",
            "conflict_reason",
        ],
    )
    write_csv(out / "subject_coverage_relaxed_private.csv", coverage)
    write_csv(
        out / "multimodal_complete_relaxed_private.csv",
        [row for row in coverage if row["multimodal_E_and_pre_rest_complete"]],
    )
    write_csv(
        out / "remaining_missing_components_private.csv",
        [row for row in coverage if not row["multimodal_E_and_pre_rest_complete"]],
    )
    write_csv(out / "derived_signal_relaxed_resolution_private.csv", reassigned)

    counts = {
        "subjects": len(subjects),
        "identity_evidence_pairs": len(collapsed),
        "accepted_file_links": len(links),
        "unresolved_ambiguous_identity_pairs": len(conflicts),
        "unresolved_tied_identity_pairs": len(
            {
                (str(row["recording_code"]), str(row["filename_abbr"]))
                for row in conflicts
                if row["conflict_reason"]
                == "code_abbreviation_pair_has_tied_top_distinct_identities"
            }
        ),
        "rejected_lower_ranked_identity_evidence_rows": sum(
            row["conflict_reason"] == "lower_ranked_identity_evidence_rejected"
            for row in conflicts
        ),
        "unresolved_date_code_sessions": len(session_conflicts),
        "source_workbook_name_overrides_stale_legacy_name_rows": sum(
            row["resolution"]
            == "source_workbook_code_vas_identity_overrides_stale_legacy_name"
            for row in mapping_reassignment_audit
        ),
        "source_workbook_name_overrides_stale_legacy_name_subjects": len(
            {
                row["mapping_subject_id"]
                for row in mapping_reassignment_audit
                if row["resolution"]
                == "source_workbook_code_vas_identity_overrides_stale_legacy_name"
            }
        ),
        "reviewed_mapping_rows_resolved_as_one_character_abbreviation_variant": sum(
            row["resolution"]
            == "same_source_identity_reviewed_one_character_abbreviation_variant"
            for row in mapping_reassignment_audit
        ),
        "reviewed_mapping_rows_resolved_as_larger_abbreviation_variant": sum(
            row["resolution"] == "same_source_identity_reviewed_abbreviation_variant"
            for row in mapping_reassignment_audit
        ),
        "reviewed_mapping_rows_unresolved": sum(
            row["resolution"] == "unresolved_mapping_without_verified_subject"
            for row in mapping_reassignment_audit
        ),
        "subjects_with_electrophysiology_E_and_pre_rest": sum(
            row["electrophysiology_E_and_pre_rest"] for row in coverage
        ),
        "subjects_with_fnirs_E_and_pre_rest": sum(
            row["fnirs_E_and_pre_rest"] for row in coverage
        ),
        "subjects_with_multimodal_E_and_pre_rest_complete": sum(
            row["multimodal_E_and_pre_rest_complete"] for row in coverage
        ),
        "subjects_remaining_incomplete": sum(
            not row["multimodal_E_and_pre_rest_complete"] for row in coverage
        ),
        "subjects_using_relaxed_evidence": sum(
            row["uses_relaxed_evidence"] for row in coverage
        ),
        "derived_files_filename_identity_confirmed": sum(
            row["relaxed_resolution_status"] == "filename_identity_confirmed"
            for row in reassigned
        ),
        "derived_files_reassigned": sum(
            row["relaxed_resolution_status"] == "reassigned_by_source_code_abbreviation"
            for row in reassigned
        ),
        "derived_files_unresolved": sum(
            row["relaxed_resolution_status"] == "unresolved_no_unique_identity_owner"
            for row in reassigned
        ),
    }
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "E capsaicin trial plus N/C pre-capsaicin rest; A/P/T excluded",
        "status": "identity_and_file_mapping_only_not_signal_qc",
        "rules": [
            "Current code plus legacy abbreviation is strict only when the legacy name agrees with the source-workbook name.",
            "The source-workbook name plus exact VAS bridge is the identity anchor when a later legacy integration-table name has shifted.",
            "A reviewed mapping-table stem under the verified workbook code remains linked to that current VAS row; abbreviation disagreements are retained as variants rather than redirected by stale names.",
            "Exact source-workbook Chinese name may connect historical code and abbreviation from the same legacy row.",
            "High-confidence exact-name chat evidence requires date, code, and an observed filename abbreviation.",
            "A one-character name variant additionally requires a unique VAS bridge and abbreviation consistency.",
            "A code-abbreviation pair pointing to multiple distinct name-plus-VAS identities is not auto-assigned.",
            "Shared historical recordings are not independent observations.",
        ],
        "counts": counts,
        "inputs": {
            str(path): digest(path)
            for path in (
                merged_path,
                strict_files_path,
                strict_mapping_path,
                old_subject_path,
                chat_path,
                provenance_path,
            )
        },
        "software": {"python": sys.version, "platform": platform.platform()},
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(out), **counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
