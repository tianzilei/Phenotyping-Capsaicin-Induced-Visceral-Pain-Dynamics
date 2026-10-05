"""Locate electrophysiology and fNIRS E/N/C recordings for 216 subjects.

N and C are pre-capsaicin resting recordings; E is the oral capsaicin trial.
The script makes a read-only inventory and never copies or edits source data.
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = {"E": "capsaicin_trial", "N": "pre_capsaicin_rest", "C": "pre_capsaicin_rest"}
SIGNAL_EXTS = {
    ".acq",
    ".omm",
    ".ext",
    ".pat",
    ".asc",
    ".txt",
    ".csv",
    ".snirf",
    ".nirs",
    ".hdr",
    ".wl1",
    ".wl2",
}
# Some acquisition names omit the leading zero of a three-digit code (for
# example, 058 is written as 58).  The case of both abbreviations and stages is
# also inconsistent.  Parsing is deliberately structural and never fuzzy.
PREFIX = re.compile(
    r"^(?P<date>20\d{6})(?P<code>\d{2,3})(?P<abbr>[A-Za-z]{4})(?P<tail>[^.]*)$",
    re.I,
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def clean_code(value: object) -> str:
    match = re.search(r"\d+", str(value or ""))
    return str(int(match.group())) if match else ""


def vas_signature(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        str(row.get(f"VAS_{minute}min", "")).strip() for minute in range(1, 21)
    )


def parse_recording_name(name: str) -> dict[str, str] | None:
    """Parse a recording filename without guessing a person's identity."""
    stem = Path(name).stem
    if stem.lower().endswith("_egg"):
        stem = stem[:-4]
    match = PREFIX.match(stem)
    if not match:
        return None
    acquisition_token = match.group("tail").split("_")[0]
    phase_letters = re.findall(r"[A-Za-z]", acquisition_token)
    phase = phase_letters[-1].upper() if phase_letters else ""
    return {
        "date": match.group("date"),
        "recording_code": clean_code(match.group("code")),
        "filename_abbr": match.group("abbr").upper(),
        "phase": phase,
        "stage": phase if phase in STAGES else "",
        "filename_tail": acquisition_token,
    }


def read_csv_any(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            return list(csv.DictReader(raw.decode(encoding).splitlines()))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {path}")


def classify_file(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    text = str(path).lower().replace("/", "\\")
    if ext == ".acq":
        return "electrophysiology", "raw_biopac"
    if ext == ".csv" and path.parent.name.lower() == "biopac_csv":
        return "electrophysiology_multichannel", "full_biopac_csv"
    if ext == ".csv" and "biopac_csv" in text and "\\ecg\\" in text:
        return "electrophysiology_ecg", "derived_split_csv"
    if ext == ".csv" and "biopac_csv" in text and "\\egg\\" in text:
        return "electrophysiology_egg", "derived_split_csv"
    if ext == ".csv" and "biopac_csv" in text and "\\emg\\" in text:
        return "electrophysiology_emg", "derived_split_csv"
    if ext in {".omm", ".ext", ".pat", ".asc", ".wl1", ".wl2", ".hdr"}:
        return "fnirs", "raw_or_companion"
    if ext in {".snirf", ".nirs"}:
        return "fnirs", "converted_container"
    if ext in {".txt", ".csv"} and ("fnirs" in text or "nirs" in text):
        return "fnirs", "converted_text_or_metadata"
    return "unknown", "candidate_companion"


def scan_f() -> list[dict[str, object]]:
    output = []
    for root, _, files in os.walk("F:/"):
        for name in files:
            path = Path(root) / name
            if name.startswith("._") or path.suffix.lower() not in SIGNAL_EXTS:
                continue
            parsed = parse_recording_name(name)
            if not parsed or parsed["stage"] not in STAGES:
                continue
            modality, source_level = classify_file(path)
            try:
                stat = path.stat()
            except OSError:
                continue
            output.append(
                {
                    "path": str(path),
                    "filename": name,
                    "extension": path.suffix.lower(),
                    "bytes": stat.st_size,
                    "modified_utc": datetime.fromtimestamp(
                        stat.st_mtime, timezone.utc
                    ).isoformat(),
                    "date": parsed["date"],
                    "recording_code": parsed["recording_code"],
                    "filename_abbr": parsed["filename_abbr"],
                    "filename_tail": parsed["filename_tail"],
                    "stage": parsed["stage"],
                    "stage_meaning": STAGES[parsed["stage"]],
                    "modality": modality,
                    "source_level": source_level,
                }
            )
    return output


def hash_derived_provenance(
    old_dir: Path, current_dir: Path
) -> list[dict[str, object]]:
    """Reverse exact renamed copies using SHA256; do not trust legacy fuzzy maps."""
    old_files = [
        p for p in old_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv"
    ]
    current_files = [
        p for p in current_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv"
    ]
    old_by_size: dict[int, list[Path]] = defaultdict(list)
    current_by_size: dict[int, list[Path]] = defaultdict(list)
    for path in old_files:
        old_by_size[path.stat().st_size].append(path)
    for path in current_files:
        current_by_size[path.stat().st_size].append(path)
    old_hashes: dict[str, list[Path]] = defaultdict(list)
    for size, paths in old_by_size.items():
        if size in current_by_size:
            for path in paths:
                old_hashes[sha256(path)].append(path)
    rows = []
    for size, paths in current_by_size.items():
        if size not in old_by_size:
            for path in paths:
                rows.append(
                    {
                        "current_path": str(path),
                        "current_filename": path.name,
                        "bytes": size,
                        "sha256": "",
                        "old_path": "",
                        "old_filename": "",
                        "hash_match_count": 0,
                        "phase": "",
                        "stage": "",
                        "recording_code": "",
                        "filename_abbr": "",
                        "provenance_status": "no_size_candidate",
                    }
                )
            continue
        for path in paths:
            digest = sha256(path)
            matches = old_hashes.get(digest, [])
            if not matches:
                rows.append(
                    {
                        "current_path": str(path),
                        "current_filename": path.name,
                        "bytes": size,
                        "sha256": digest,
                        "old_path": "",
                        "old_filename": "",
                        "hash_match_count": 0,
                        "phase": "",
                        "stage": "",
                        "recording_code": "",
                        "filename_abbr": "",
                        "provenance_status": "no_hash_match",
                    }
                )
            for old_path in matches:
                parsed = parse_recording_name(old_path.name) or {}
                rows.append(
                    {
                        "current_path": str(path),
                        "current_filename": path.name,
                        "bytes": size,
                        "sha256": digest,
                        "old_path": str(old_path),
                        "old_filename": old_path.name,
                        "hash_match_count": len(matches),
                        "phase": parsed.get("phase", ""),
                        "stage": parsed.get("stage", ""),
                        "recording_code": parsed.get("recording_code", ""),
                        "filename_abbr": parsed.get("filename_abbr", ""),
                        "provenance_status": "unique_exact_hash"
                        if len(matches) == 1
                        else "duplicate_exact_hash",
                    }
                )
    return rows


def write_csv(
    path: Path, rows: list[dict[str, object]], fields: list[str] | None = None
) -> None:
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    merged_dirs = sorted(
        (ROOT / "02_quality_control").glob("capsaicin_baseline_merged_*"),
        key=lambda p: p.stat().st_mtime,
    )
    merged_path = merged_dirs[-1] / "capsaicin_baseline_merged_private.csv"
    subjects = read_csv_any(merged_path)
    if len(subjects) != 216:
        raise ValueError(f"Expected 216 subjects, got {len(subjects)}")
    old_root = next(
        Path("D:/") / n
        for n in os.listdir("D:/")
        if n.startswith("capsaicin") and "analysis" not in n
    )
    old_subject_path = old_root / "data" / "subject_baseline_info.csv"
    old_subjects = read_csv_any(old_subject_path)
    old_by_code = {clean_code(r["ID"]): r for r in old_subjects}
    mapping_path = (
        old_root
        / "data"
        / "processed"
        / next(
            n
            for n in os.listdir(old_root / "data" / "processed")
            if n.lower().endswith(".csv") and "fnirs" in n.lower()
        )
    )
    map_rows = read_csv_any(mapping_path)
    headers = list(map_rows[0])
    h_file, h_date, h_code, h_abbr, h_stage, h_project, h_caps, h_intervention = (
        headers[:8]
    )
    selected_map = []
    subject_by_code = {r["legacy_code_numeric"]: r for r in subjects}
    for row in map_rows:
        code = clean_code(row.get(h_code))
        stage = str(row.get(h_stage, "")).upper()
        if code not in subject_by_code or stage not in STAGES:
            continue
        subject = subject_by_code[code]
        known_abbr = str(old_by_code[code].get("name_abbr", "")).upper()
        map_abbr = str(row.get(h_abbr, "")).upper()
        selected_map.append(
            {
                "current_subject_id": subject["current_subject_id"],
                "legacy_code_numeric": code,
                "subject_name": subject["bridge_name"],
                "known_name_abbr": known_abbr,
                "map_recording_stem": row.get(h_file, ""),
                "map_date": row.get(h_date, ""),
                "map_recording_code": clean_code(row.get(h_code)),
                "map_name_abbr": map_abbr,
                "abbr_status": "exact" if known_abbr == map_abbr else "review_mismatch",
                "stage": stage,
                "stage_meaning": STAGES[stage],
                "project": row.get(h_project, ""),
                "capsaicin_flag": row.get(h_caps, ""),
                "intervention": row.get(h_intervention, ""),
            }
        )
    files = scan_f()
    file_by_path = {
        os.path.normcase(os.path.normpath(str(row["path"]))): row for row in files
    }
    by_key: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    by_identity_stage: dict[tuple[str, str, str], list[dict[str, object]]] = (
        defaultdict(list)
    )
    for file in files:
        by_key[
            (
                str(file["date"]),
                str(file["recording_code"]),
                str(file["filename_abbr"]),
                str(file["stage"]),
            )
        ].append(file)
        by_identity_stage[
            (
                str(file["recording_code"]),
                str(file["filename_abbr"]),
                str(file["stage"]),
            )
        ].append(file)
    links = []
    linked_paths = set()
    for record in selected_map:
        exact_stem = str(record["map_recording_stem"]).lower()
        identity_key = (
            str(record["map_recording_code"]),
            str(record["map_name_abbr"]),
            str(record["stage"]),
        )
        identity_matches = by_identity_stage.get(identity_key, [])
        matches = [
            f
            for f in identity_matches
            if Path(str(f["filename"])).stem.lower().startswith(exact_stem)
        ]
        link_basis = (
            "exact_mapping_stem" if matches else "exact_code_abbr_stage_across_date"
        )
        if not matches:
            matches = identity_matches
        for file in matches:
            linked_paths.add(str(file["path"]))
            links.append(
                {
                    **record,
                    **file,
                    "link_basis": link_basis,
                    "map_date_matches_filename_date": str(record["map_date"])
                    == str(file["date"]),
                }
            )
        if not matches:
            links.append(
                {
                    **record,
                    "path": "",
                    "filename": "",
                    "extension": "",
                    "bytes": "",
                    "modified_utc": "",
                    "date": "",
                    "recording_code": "",
                    "filename_abbr": "",
                    "filename_tail": "",
                    "modality": "",
                    "source_level": "",
                    "link_basis": "mapping_row_no_file_found",
                    "map_date_matches_filename_date": "",
                }
            )

    # Independently discover files for every included participant. This fills
    # gaps in the historical fNIRS mapping table without fuzzy name matching.
    discovery_links = []
    for subject in subjects:
        code = subject["legacy_code_numeric"]
        abbr = str(old_by_code[code].get("name_abbr", "")).upper()
        for stage in STAGES:
            for file in by_identity_stage.get((code, abbr, stage), []):
                discovery_links.append(
                    {
                        "current_subject_id": subject["current_subject_id"],
                        "legacy_code_numeric": code,
                        "subject_name": subject["bridge_name"],
                        "known_name_abbr": abbr,
                        **file,
                        "link_basis": "exact_included_code_name_abbr_stage",
                    }
                )
    # The chat audit establishes participation as name+date+code evidence.  Use
    # only its high-confidence exact-name rows here; typo/polyphonic variants
    # remain in the separate review artifact and are never auto-promoted.
    chat_audit_dirs = sorted(
        (ROOT / "02_quality_control").glob("chat_participant_signal_audit_*"),
        key=lambda p: p.stat().st_mtime,
    )
    chat_audit_path = chat_audit_dirs[-1] / "forward_chat_to_raw_private.csv"
    chat_rows = read_csv_any(chat_audit_path)
    subjects_by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    for subject in subjects:
        subjects_by_name[str(subject["bridge_name"]).strip()].append(subject)
    chat_links = []
    chat_link_keys = set()
    for chat in chat_rows:
        name = str(chat.get("chat_name", "")).strip()
        if (
            chat.get("confidence") != "high"
            or chat.get("name_match_status") != "exact_name"
            or name not in subjects_by_name
        ):
            continue
        for source_path in str(
            chat.get("candidate_original_signal_paths", "")
        ).splitlines():
            file = file_by_path.get(
                os.path.normcase(os.path.normpath(source_path.strip()))
            )
            if not file or file["stage"] not in STAGES:
                continue
            for subject in subjects_by_name[name]:
                key = (str(subject["current_subject_id"]), str(file["path"]))
                if key in chat_link_keys:
                    continue
                chat_link_keys.add(key)
                same_code = clean_code(chat.get("code_numeric")) == str(
                    subject["legacy_code_numeric"]
                )
                chat_links.append(
                    {
                        "current_subject_id": subject["current_subject_id"],
                        "legacy_code_numeric": subject["legacy_code_numeric"],
                        "subject_name": name,
                        "chat_date": chat.get("target_date", ""),
                        "chat_code_numeric": clean_code(chat.get("code_numeric")),
                        **file,
                        "link_basis": "chat_exact_name_date_code_same_legacy_code"
                        if same_code
                        else "chat_exact_name_date_code_historical_code",
                        "identity_status": "same_legacy_code"
                        if same_code
                        else "historical_code_same_identity_candidate",
                        "scientific_selection_status": "candidate_requires_visit_alignment"
                        if not same_code
                        else "identity_supported",
                    }
                )
    # Existing SUBJECT CSVs are retained as derived-signal candidates, not
    # evidence of a specific E/N/C stage.
    current_root = next(
        Path("D:/") / n
        for n in os.listdir("D:/")
        if n.startswith("Phenotyping Capsaicin")
    )
    derived_dir = current_root / "ecg_egg"
    old_derived_dir = old_root / "data" / "ecg_egg"
    derived_provenance = hash_derived_provenance(old_derived_dir, derived_dir)
    subject_by_sid = {str(r["current_subject_id"]): r for r in subjects}
    for row in derived_provenance:
        sid_match = re.search(r"SUBJECT\d{3}", str(row["current_filename"]), re.I)
        sid = sid_match.group().upper() if sid_match else ""
        subject = subject_by_sid.get(sid)
        expected_code = str(subject["legacy_code_numeric"]) if subject else ""
        expected_abbr = str(
            old_by_code.get(expected_code, {}).get("name_abbr", "")
        ).upper()
        row["current_subject_id"] = sid
        row["expected_legacy_code_numeric"] = expected_code
        row["expected_name_abbr"] = expected_abbr
        row["recording_code_matches_expected"] = bool(
            expected_code and str(row["recording_code"]) == expected_code
        )
        row["filename_abbr_matches_expected"] = bool(
            expected_abbr and str(row["filename_abbr"]).upper() == expected_abbr
        )
        row["identity_provenance_status"] = (
            "exact_hash_and_identity"
            if row["provenance_status"] in {"unique_exact_hash", "duplicate_exact_hash"}
            and row["recording_code_matches_expected"]
            and row["filename_abbr_matches_expected"]
            else "exact_hash_identity_conflict"
            if row["provenance_status"] in {"unique_exact_hash", "duplicate_exact_hash"}
            and subject
            else "hash_provenance_unresolved"
        )
    provenance_by_current = defaultdict(list)
    for row in derived_provenance:
        provenance_by_current[str(row["current_filename"])].append(row)
    derived = []
    for i in range(1, 217):
        sid = f"SUBJECT{i:03d}"
        for modality, suffix in (("electrophysiology", ".csv"), ("egg", "_egg.csv")):
            path = derived_dir / f"{sid}{suffix}"
            prov = provenance_by_current.get(path.name, [])
            exact = [
                r
                for r in prov
                if r["provenance_status"]
                in {"unique_exact_hash", "duplicate_exact_hash"}
            ]
            identity_exact = [
                r
                for r in prov
                if r["identity_provenance_status"] == "exact_hash_and_identity"
            ]
            identity_conflict = [
                r
                for r in prov
                if r["identity_provenance_status"] == "exact_hash_identity_conflict"
            ]
            verified_stages = sorted(
                {str(r["stage"]) for r in exact if r["stage"] in STAGES}
            )
            derived.append(
                {
                    "current_subject_id": sid,
                    "modality": modality,
                    "path": str(path),
                    "exists": path.is_file(),
                    "bytes": path.stat().st_size if path.is_file() else "",
                    "stage": ";".join(verified_stages)
                    if verified_stages
                    else "unverified_existing_derivative",
                    "source_level": "derived_csv",
                    "exact_hash_source_count": len(exact),
                    "exact_hash_source_names": ";".join(
                        sorted({str(r["old_filename"]) for r in exact})
                    ),
                    "identity_provenance_status": "exact_hash_and_identity"
                    if identity_exact
                    else "exact_hash_identity_conflict"
                    if identity_conflict
                    else "hash_provenance_unresolved",
                }
            )
    subject_summary = []
    for subject in subjects:
        sid = subject["current_subject_id"]
        recs = [r for r in selected_map if r["current_subject_id"] == sid]
        subject_links = [r for r in discovery_links if r["current_subject_id"] == sid]
        stage_set = {r["stage"] for r in recs}
        file_stage = {r["stage"] for r in subject_links}
        modalities = defaultdict(set)
        for r in subject_links:
            modalities[str(r.get("modality"))].add(str(r["stage"]))
        electro_modalities = {
            "electrophysiology",
            "electrophysiology_multichannel",
            "electrophysiology_ecg",
            "electrophysiology_egg",
            "electrophysiology_emg",
        }
        electro_stages = {
            str(r["stage"])
            for r in subject_links
            if str(r.get("modality")) in electro_modalities
        }
        fnirs_stages = modalities["fnirs"]
        subject_summary.append(
            {
                "current_subject_id": sid,
                "legacy_code_numeric": subject["legacy_code_numeric"],
                "subject_name": subject["bridge_name"],
                "known_name_abbr": old_by_code[subject["legacy_code_numeric"]].get(
                    "name_abbr", ""
                ),
                "mapping_E": "E" in stage_set,
                "mapping_pre_rest_N_or_C": bool(stage_set & {"N", "C"}),
                "file_E_any": "E" in file_stage,
                "file_pre_rest_N_or_C_any": bool(file_stage & {"N", "C"}),
                "raw_biopac_E": any(
                    r.get("modality") == "electrophysiology"
                    and r["stage"] == "E"
                    and r.get("source_level") == "raw_biopac"
                    for r in subject_links
                ),
                "raw_biopac_pre_rest": any(
                    r.get("modality") == "electrophysiology"
                    and r["stage"] in {"N", "C"}
                    and r.get("source_level") == "raw_biopac"
                    for r in subject_links
                ),
                "full_biopac_csv_E": any(
                    r.get("modality") == "electrophysiology_multichannel"
                    and r["stage"] == "E"
                    for r in subject_links
                ),
                "full_biopac_csv_pre_rest": any(
                    r.get("modality") == "electrophysiology_multichannel"
                    and r["stage"] in {"N", "C"}
                    for r in subject_links
                ),
                "ecg_csv_E": any(
                    r.get("modality") == "electrophysiology_ecg" and r["stage"] == "E"
                    for r in subject_links
                ),
                "ecg_csv_pre_rest": any(
                    r.get("modality") == "electrophysiology_ecg"
                    and r["stage"] in {"N", "C"}
                    for r in subject_links
                ),
                "egg_csv_E": any(
                    r.get("modality") == "electrophysiology_egg" and r["stage"] == "E"
                    for r in subject_links
                ),
                "egg_csv_pre_rest": any(
                    r.get("modality") == "electrophysiology_egg"
                    and r["stage"] in {"N", "C"}
                    for r in subject_links
                ),
                "fnirs_E": "E" in modalities["fnirs"],
                "fnirs_pre_rest": bool(modalities["fnirs"] & {"N", "C"}),
                "electrophysiology_E_any": "E" in electro_stages,
                "electrophysiology_pre_rest_any": bool(electro_stages & {"N", "C"}),
                "electrophysiology_E_and_pre_rest": bool(
                    "E" in electro_stages and electro_stages & {"N", "C"}
                ),
                "fnirs_E_and_pre_rest": bool(
                    "E" in fnirs_stages and fnirs_stages & {"N", "C"}
                ),
                "multimodal_E_and_pre_rest_complete": bool(
                    "E" in electro_stages
                    and electro_stages & {"N", "C"}
                    and "E" in fnirs_stages
                    and fnirs_stages & {"N", "C"}
                ),
                "map_record_count": len(recs),
                "linked_file_count": len(subject_links),
                "identity_review_required": any(
                    r["abbr_status"] != "exact" for r in recs
                ),
                "coverage_status": "E_and_pre_rest_found"
                if "E" in file_stage and file_stage & {"N", "C"}
                else "missing_E"
                if "E" not in file_stage
                else "missing_pre_rest",
            }
        )
    # A subset of the 216 study rows repeats the same person and exact VAS
    # trajectory under historical project codes.  Keep all study rows, but
    # expose any reused signal as shared rather than pretending it is an
    # independent recording.
    identity_groups: dict[tuple[str, tuple[str, ...]], list[dict[str, str]]] = (
        defaultdict(list)
    )
    for subject in subjects:
        identity_groups[
            (str(subject["bridge_name"]).strip(), vas_signature(subject))
        ].append(subject)
    summary_by_sid = {str(r["current_subject_id"]): r for r in subject_summary}
    links_by_sid = defaultdict(list)
    for link in discovery_links:
        links_by_sid[str(link["current_subject_id"])].append(link)
    chat_links_by_sid = defaultdict(list)
    for link in chat_links:
        chat_links_by_sid[str(link["current_subject_id"])].append(link)
    shared_links = []
    identity_summary = []
    for group in identity_groups.values():
        group_ids = sorted(str(r["current_subject_id"]) for r in group)
        group_summaries = [summary_by_sid[group_sid] for group_sid in group_ids]
        identity_electro_E = any(r["electrophysiology_E_any"] for r in group_summaries)
        identity_electro_rest = any(
            r["electrophysiology_pre_rest_any"] for r in group_summaries
        )
        identity_fnirs_E = any(r["fnirs_E"] for r in group_summaries)
        identity_fnirs_rest = any(r["fnirs_pre_rest"] for r in group_summaries)
        identity_summary.append(
            {
                "subject_name": group[0]["bridge_name"],
                "vas_signature_sha256": hashlib.sha256(
                    "|".join(vas_signature(group[0])).encode("utf-8")
                ).hexdigest(),
                "study_record_count": len(group_ids),
                "current_subject_ids": ";".join(group_ids),
                "legacy_codes": ";".join(
                    sorted(
                        (str(r["legacy_code_numeric"]) for r in group),
                        key=lambda x: int(x),
                    )
                ),
                "electrophysiology_E": identity_electro_E,
                "electrophysiology_pre_rest": identity_electro_rest,
                "electrophysiology_E_and_pre_rest": bool(
                    identity_electro_E and identity_electro_rest
                ),
                "fnirs_E": identity_fnirs_E,
                "fnirs_pre_rest": identity_fnirs_rest,
                "fnirs_E_and_pre_rest": bool(identity_fnirs_E and identity_fnirs_rest),
                "multimodal_E_and_pre_rest_complete": bool(
                    identity_electro_E
                    and identity_electro_rest
                    and identity_fnirs_E
                    and identity_fnirs_rest
                ),
                "independence_note": "one_identity_multiple_study_rows"
                if len(group_ids) > 1
                else "one_identity_one_study_row",
            }
        )
        for subject in group:
            sid = str(subject["current_subject_id"])
            summary = summary_by_sid[sid]
            own_stages = {str(r["stage"]) for r in links_by_sid[sid]}
            chat_stages = {str(r["stage"]) for r in chat_links_by_sid[sid]}
            donor_ids_e = sorted(
                other
                for other in group_ids
                if other != sid
                and any(str(r["stage"]) == "E" for r in links_by_sid[other])
            )
            donor_ids_rest = sorted(
                other
                for other in group_ids
                if other != sid
                and any(str(r["stage"]) in {"N", "C"} for r in links_by_sid[other])
            )
            summary.update(
                {
                    "identity_group_size": len(group_ids),
                    "identity_group_subject_ids": ";".join(group_ids),
                    "shared_source_from_subject_ids_E": ";".join(donor_ids_e)
                    if "E" not in own_stages
                    else "",
                    "shared_source_from_subject_ids_pre_rest": ";".join(donor_ids_rest)
                    if not (own_stages & {"N", "C"})
                    else "",
                    "identity_level_E": bool("E" in own_stages or donor_ids_e),
                    "identity_level_pre_rest": bool(
                        own_stages & {"N", "C"} or donor_ids_rest
                    ),
                    "identity_coverage_status": (
                        "E_and_pre_rest_found"
                        if ("E" in own_stages or donor_ids_e)
                        and (own_stages & {"N", "C"} or donor_ids_rest)
                        else "missing_E"
                        if not ("E" in own_stages or donor_ids_e)
                        else "missing_pre_rest"
                    ),
                    "shared_source_recording": bool(
                        ("E" not in own_stages and donor_ids_e)
                        or (not (own_stages & {"N", "C"}) and donor_ids_rest)
                    ),
                    "chat_exact_name_E_candidate": "E" in chat_stages,
                    "chat_exact_name_pre_rest_candidate": bool(
                        chat_stages & {"N", "C"}
                    ),
                    "expanded_identity_E_candidate": bool(
                        "E" in own_stages or donor_ids_e or "E" in chat_stages
                    ),
                    "expanded_identity_pre_rest_candidate": bool(
                        own_stages & {"N", "C"}
                        or donor_ids_rest
                        or chat_stages & {"N", "C"}
                    ),
                    "expanded_identity_coverage_status": (
                        "E_and_pre_rest_candidate"
                        if ("E" in own_stages or donor_ids_e or "E" in chat_stages)
                        and (
                            own_stages & {"N", "C"}
                            or donor_ids_rest
                            or chat_stages & {"N", "C"}
                        )
                        else "missing_E_candidate"
                        if not ("E" in own_stages or donor_ids_e or "E" in chat_stages)
                        else "missing_pre_rest_candidate"
                    ),
                    "identity_level_electrophysiology_E_and_pre_rest": bool(
                        identity_electro_E and identity_electro_rest
                    ),
                    "identity_level_fnirs_E_and_pre_rest": bool(
                        identity_fnirs_E and identity_fnirs_rest
                    ),
                    "identity_level_multimodal_E_and_pre_rest_complete": bool(
                        identity_electro_E
                        and identity_electro_rest
                        and identity_fnirs_E
                        and identity_fnirs_rest
                    ),
                }
            )
            needed = ({"E"} if "E" not in own_stages else set()) | (
                {"N", "C"} if not (own_stages & {"N", "C"}) else set()
            )
            for donor_sid in group_ids:
                if donor_sid == sid:
                    continue
                for link in links_by_sid[donor_sid]:
                    if str(link["stage"]) not in needed:
                        continue
                    shared_links.append(
                        {
                            **link,
                            "current_subject_id": sid,
                            "recipient_legacy_code_numeric": subject[
                                "legacy_code_numeric"
                            ],
                            "source_subject_id": donor_sid,
                            "source_legacy_code_numeric": summary_by_sid[donor_sid][
                                "legacy_code_numeric"
                            ],
                            "link_basis": "shared_source_recording_exact_name_and_vas_signature",
                            "independence_status": "not_an_independent_recording",
                        }
                    )
    reverse = []
    linked_key_set = {
        (
            str(r.get("date")),
            str(r.get("recording_code")),
            str(r.get("filename_abbr")),
            str(r.get("stage")),
        )
        for r in links
        if r.get("path")
    }
    for file in files:
        key = (
            str(file["date"]),
            str(file["recording_code"]),
            str(file["filename_abbr"]),
            str(file["stage"]),
        )
        reverse.append(
            {
                **file,
                "selected_216_mapping_match": key in linked_key_set,
                "reverse_status": "linked_to_selected_subject"
                if key in linked_key_set
                else "not_linked_to_selected_216",
            }
        )
    out = (
        ROOT
        / "02_quality_control"
        / f"enc_signal_inventory_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    out.mkdir(parents=True)
    write_csv(out / "selected_enc_mapping_private.csv", selected_map)
    write_csv(out / "forward_subject_to_files_private.csv", links)
    write_csv(out / "identity_discovered_subject_to_files_private.csv", discovery_links)
    write_csv(out / "reverse_files_to_subject_private.csv", reverse)
    write_csv(out / "subject_coverage_private.csv", subject_summary)
    write_csv(out / "identity_coverage_private.csv", identity_summary)
    write_csv(
        out / "strict_multimodal_complete_private.csv",
        [r for r in subject_summary if r["multimodal_E_and_pre_rest_complete"]],
    )
    write_csv(
        out / "subjects_missing_signal_components_private.csv",
        [r for r in subject_summary if not r["multimodal_E_and_pre_rest_complete"]],
    )
    write_csv(out / "existing_derived_signals_private.csv", derived)
    write_csv(out / "derived_signal_hash_provenance_private.csv", derived_provenance)
    write_csv(out / "identity_shared_subject_to_files_private.csv", shared_links)
    write_csv(out / "chat_exact_name_enc_candidates_private.csv", chat_links)
    file_metadata_hash = hashlib.sha256(
        "\n".join(
            sorted(f"{r['path']}|{r['bytes']}|{r['modified_utc']}" for r in files)
        ).encode("utf-8")
    ).hexdigest()
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "216 included capsaicin subjects; E trial plus N/C pre-capsaicin rest; A/P/T excluded",
        "stage_semantics": STAGES,
        "counts": {
            "subjects": len(subjects),
            "selected_mapping_rows": len(selected_map),
            "F_enc_candidate_files": len(files),
            "linked_file_rows": sum(bool(r.get("path")) for r in links),
            "subjects_with_any_mapping": len(
                {r["current_subject_id"] for r in selected_map}
            ),
            "subjects_with_E_mapping": sum(r["mapping_E"] for r in subject_summary),
            "subjects_with_pre_rest_mapping": sum(
                r["mapping_pre_rest_N_or_C"] for r in subject_summary
            ),
            "subjects_with_E_and_pre_rest_files": sum(
                r["coverage_status"] == "E_and_pre_rest_found" for r in subject_summary
            ),
            "subjects_missing_E_file": sum(
                r["coverage_status"] == "missing_E" for r in subject_summary
            ),
            "subjects_missing_pre_rest_file": sum(
                r["coverage_status"] == "missing_pre_rest" for r in subject_summary
            ),
            "identity_level_subject_rows_with_E_and_pre_rest": sum(
                r["identity_coverage_status"] == "E_and_pre_rest_found"
                for r in subject_summary
            ),
            "identity_level_subject_rows_missing_E": sum(
                r["identity_coverage_status"] == "missing_E" for r in subject_summary
            ),
            "identity_level_subject_rows_missing_pre_rest": sum(
                r["identity_coverage_status"] == "missing_pre_rest"
                for r in subject_summary
            ),
            "subject_rows_using_shared_source_recording": sum(
                r["shared_source_recording"] for r in subject_summary
            ),
            "unique_exact_name_vas_identities": len(identity_groups),
            "subject_rows_with_chat_exact_name_E_candidate": sum(
                r["chat_exact_name_E_candidate"] for r in subject_summary
            ),
            "subject_rows_with_chat_exact_name_pre_rest_candidate": sum(
                r["chat_exact_name_pre_rest_candidate"] for r in subject_summary
            ),
            "expanded_identity_subject_rows_with_E_and_pre_rest_candidate": sum(
                r["expanded_identity_coverage_status"] == "E_and_pre_rest_candidate"
                for r in subject_summary
            ),
            "expanded_identity_subject_rows_missing_E_candidate": sum(
                r["expanded_identity_coverage_status"] == "missing_E_candidate"
                for r in subject_summary
            ),
            "expanded_identity_subject_rows_missing_pre_rest_candidate": sum(
                r["expanded_identity_coverage_status"] == "missing_pre_rest_candidate"
                for r in subject_summary
            ),
            "subjects_with_raw_biopac_E": sum(
                r["raw_biopac_E"] for r in subject_summary
            ),
            "subjects_with_raw_biopac_pre_rest": sum(
                r["raw_biopac_pre_rest"] for r in subject_summary
            ),
            "subjects_with_full_biopac_csv_E": sum(
                r["full_biopac_csv_E"] for r in subject_summary
            ),
            "subjects_with_full_biopac_csv_pre_rest": sum(
                r["full_biopac_csv_pre_rest"] for r in subject_summary
            ),
            "subjects_with_ecg_csv_E": sum(r["ecg_csv_E"] for r in subject_summary),
            "subjects_with_ecg_csv_pre_rest": sum(
                r["ecg_csv_pre_rest"] for r in subject_summary
            ),
            "subjects_with_egg_csv_E": sum(r["egg_csv_E"] for r in subject_summary),
            "subjects_with_egg_csv_pre_rest": sum(
                r["egg_csv_pre_rest"] for r in subject_summary
            ),
            "subjects_with_fnirs_E": sum(r["fnirs_E"] for r in subject_summary),
            "subjects_with_fnirs_pre_rest": sum(
                r["fnirs_pre_rest"] for r in subject_summary
            ),
            "subjects_with_electrophysiology_E_and_pre_rest": sum(
                r["electrophysiology_E_and_pre_rest"] for r in subject_summary
            ),
            "subjects_with_fnirs_E_and_pre_rest": sum(
                r["fnirs_E_and_pre_rest"] for r in subject_summary
            ),
            "subjects_with_multimodal_E_and_pre_rest_complete": sum(
                r["multimodal_E_and_pre_rest_complete"] for r in subject_summary
            ),
            "identity_level_subject_rows_with_electrophysiology_E_and_pre_rest": sum(
                r["identity_level_electrophysiology_E_and_pre_rest"]
                for r in subject_summary
            ),
            "identity_level_subject_rows_with_fnirs_E_and_pre_rest": sum(
                r["identity_level_fnirs_E_and_pre_rest"] for r in subject_summary
            ),
            "identity_level_subject_rows_with_multimodal_E_and_pre_rest_complete": sum(
                r["identity_level_multimodal_E_and_pre_rest_complete"]
                for r in subject_summary
            ),
            "unique_identities_with_electrophysiology_E_and_pre_rest": sum(
                r["electrophysiology_E_and_pre_rest"] for r in identity_summary
            ),
            "unique_identities_with_fnirs_E_and_pre_rest": sum(
                r["fnirs_E_and_pre_rest"] for r in identity_summary
            ),
            "unique_identities_with_multimodal_E_and_pre_rest_complete": sum(
                r["multimodal_E_and_pre_rest_complete"] for r in identity_summary
            ),
            "identity_review_subjects": sum(
                r["identity_review_required"] for r in subject_summary
            ),
            "existing_derived_subject_csv_pairs": sum(r["exists"] for r in derived)
            // 2,
            "derived_files_with_exact_hash_provenance": len(
                {
                    r["current_filename"]
                    for r in derived_provenance
                    if r["provenance_status"]
                    in {"unique_exact_hash", "duplicate_exact_hash"}
                }
            ),
            "derived_subject_files_with_exact_identity_provenance": len(
                {
                    r["current_filename"]
                    for r in derived_provenance
                    if r["identity_provenance_status"] == "exact_hash_and_identity"
                }
            ),
            "derived_subject_files_with_identity_conflict": len(
                {
                    r["current_filename"]
                    for r in derived_provenance
                    if r["identity_provenance_status"] == "exact_hash_identity_conflict"
                }
            ),
            "derived_subject_files_with_unresolved_hash_provenance": len(
                {
                    r["current_filename"]
                    for r in derived_provenance
                    if r["current_subject_id"]
                    and r["identity_provenance_status"] == "hash_provenance_unresolved"
                }
            ),
            "derived_subject_pairs_with_exact_identity_provenance": sum(
                all(
                    any(
                        r["identity_provenance_status"] == "exact_hash_and_identity"
                        for r in provenance_by_current.get(f"{sid}{suffix}", [])
                    )
                    for suffix in (".csv", "_egg.csv")
                )
                for sid in (f"SUBJECT{i:03d}" for i in range(1, 217))
            ),
        },
        "inputs": {
            str(merged_path): sha256(merged_path),
            str(old_subject_path): sha256(old_subject_path),
            str(mapping_path): sha256(mapping_path),
            str(chat_audit_path): sha256(chat_audit_path),
            "F_file_metadata_sha256": file_metadata_hash,
        },
        "limitations": [
            "Primary file links require exact recording code+name abbreviation+E/N/C stage; dates are retained for audit but are not a hard identity key.",
            "Hash provenance establishes byte identity of derived files, not scientific signal quality.",
            "Source signal files are referenced in place and not copied.",
        ],
        "software": {"python": sys.version, "platform": platform.platform()},
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"output": str(out), **manifest["counts"]}, ensure_ascii=False, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
