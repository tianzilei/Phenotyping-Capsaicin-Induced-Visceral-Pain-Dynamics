"""Extend private recording linkage; distinguish supported links from candidates.

Never use a fuzzy hit as proof of a visit or promote unknown phases to E/N/C.
Source data and previous runs remain read-only. Uses only the standard library.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_relaxed_enc_mapping import (
    ROOT,
    ELECTRO,
    read_csv,
    write_csv,
    digest,
    code,
    normalize_name,
    source_identity_name,
    vas_signature,
    levenshtein,
    split_tokens,
)
from build_enc_signal_inventory import classify_file, SIGNAL_EXTS, STAGES

ALL_STAGES = {"E", "N", "C", "P"}


def parse_extended(name: str) -> dict[str, str] | None:
    if name.startswith("._"):
        return None
    stem = Path(name).stem
    # The suffix is an accidental duplication of the container extension.
    stem = re.sub(r"acq$", "", stem, flags=re.I)
    token = stem.split("_")[0]
    match = re.fullmatch(r"(20\d{6})(\d{1,3})?([A-Za-z]*)", token)
    if not match:
        return None
    date, numeric, letters = match.groups()
    try:
        datetime.strptime(date, "%Y%m%d")
    except ValueError:
        return None
    letters = letters.upper()
    # Four letters alone are an abbreviation, not an inferred phase.
    if len(letters) == 1 and letters in ALL_STAGES:
        abbr, stage = "", letters
    elif len(letters) >= 5 and re.fullmatch(r"[A-Z]{4}(?:[NCE]+|P)", letters):
        abbr, stage = letters[:4], letters[-1]
    elif len(letters) == 4 and letters[-1] in ALL_STAGES:
        # Ambiguous: e.g. LSH+E versus an unphased four-letter abbreviation.
        abbr, stage = letters[:3], letters[-1]
        return {
            "date": date,
            "recording_code": code(numeric),
            "filename_abbr": abbr,
            "stage": stage,
            "parse_rule": "three_letter_abbreviation_requires_anchor",
        }
    elif len(letters) == 4:
        abbr, stage = letters, ""
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
            r["modality"] in ELECTRO and r["stage"] == "E" for r in rows
        ),
        "electrophysiology_pre_rest": any(
            r["modality"] in ELECTRO and r["stage"] in set(rest_stages) for r in rows
        ),
        "fnirs_E": any(r["modality"] == "fnirs" and r["stage"] == "E" for r in rows),
        "fnirs_pre_rest": any(
            r["modality"] == "fnirs" and r["stage"] in set(rest_stages) for r in rows
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
    return file["filename_abbr"] + file["stage"] in alias_owners and not complementary


def resolve_claims(claims, identities, existing_owners):
    """Resolve independently per file; scores are rule priorities, not probabilities."""
    accepted, review = [], []
    grouped = defaultdict(list)
    for row in claims:
        grouped[row["path"]].append(row)
    for path, rows in grouped.items():
        best = max(r["priority"] for r in rows)
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
    return accepted, review


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "config/enc_matching_v3.json"
    )
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    allowed_stages = set(cfg["allowed_stages"])
    if (
        not set(STAGES) <= allowed_stages <= ALL_STAGES
        or cfg["allow_unknown_phase_as_complete"]
    ):
        raise ValueError("This audit requires explicit E/N/C/P phases")
    rest_stages = tuple(cfg.get("rest_stages", ["N", "C"]))
    if (
        not {"N", "C"} <= set(rest_stages) <= {"N", "C", "P"}
        or not set(rest_stages) <= allowed_stages
    ):
        raise ValueError("Only P may supplement N/C; E cannot serve as rest")
    base = args.base_run.resolve()
    manifest_path = base / "run_manifest.json"
    old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inputs = [Path(p) for p in old_manifest["inputs"]]

    def source(ending):
        return next(p for p in inputs if p.name == ending)

    subjects_path = source("capsaicin_baseline_merged_private.csv")
    files_path = source("reverse_files_to_subject_private.csv")
    chat_path = source("forward_chat_to_raw_private.csv")
    subjects = read_csv(subjects_path)
    by_sid = {s["current_subject_id"]: s for s in subjects}
    identities = {
        sid: (normalize_name(source_identity_name(s)), vas_signature(s))
        for sid, s in by_sid.items()
    }
    names = defaultdict(set)
    for sid, key in identities.items():
        if key[0]:
            names[key[0]].add(sid)
    links_path = base / "accepted_subject_to_files_private.csv"
    evidence_path = base / "identity_evidence_private.csv"
    base_links = read_csv(links_path)
    evidence = read_csv(evidence_path)
    files = {r["path"]: r for r in read_csv(files_path)}
    old_subject_path = source("subject_baseline_info.csv")
    mapping_path = next(
        p
        for p in (old_subject_path.parent / "processed").glob("*.csv")
        if "fnirs" in p.name.lower()
    )
    mappings = read_csv(mapping_path)
    aliases = defaultdict(set)
    alias_sources = defaultdict(set)

    def alias(sid, abbr, origin):
        if re.fullmatch("[A-Z]{3,4}", abbr):
            aliases[sid].add(abbr)
            alias_sources[(sid, abbr)].add(origin)

    # Lower-ranked rejected chat evidence must not seed another expansion.
    for r in base_links:
        alias(r["current_subject_id"], r["filename_abbr"], "previous_accepted_link")
    for r in evidence:
        if str(r["evidence_score"]) in {"100", "98", "90", "85"}:
            alias(
                r["current_subject_id"], r["filename_abbr"], "source_identity_evidence"
            )
    by_code = defaultdict(set)
    for sid, s in by_sid.items():
        by_code[s["legacy_code_numeric"]].add(sid)
    # Non-E/N/C mapping rows corroborate spelling only, never phase coverage.
    fields = list(mappings[0])
    for r in mappings:
        for sid in by_code.get(code(r[fields[2]]), set()):
            alias(
                sid,
                r[fields[3]].strip().upper(),
                "reviewed_mapping_alias_under_source_workbook_code",
            )
    chats = read_csv(chat_path)
    chat_sessions = defaultdict(set)
    chat_pairs = defaultdict(set)
    chat_date_alias = defaultdict(set)
    for r in chats:
        sids = names.get(normalize_name(r["chat_name"]), set())
        if not unique_identity(sids, identities):
            continue
        if r["confidence"] not in {"medium", "high"}:
            continue
        # Exact source name plus scheduling date supports a missing numeric code;
        # a discovered recording is still required before it counts as coverage.
        for sid in sids:
            for abbr in aliases[sid]:
                chat_date_alias[(r["target_date"].replace("-", ""), abbr)].add(sid)
        for abbr in split_tokens(r["filename_abbreviations"]):
            if any(abbr in aliases[sid] for sid in sids):
                chat_sessions[
                    (r["target_date"].replace("-", ""), r["code_numeric"], abbr)
                ].update(sids)
                chat_pairs[(r["code_numeric"], abbr)].update(sids)
    scan_errors, discovered, unknown = [], [], []

    def onerror(error):
        scan_errors.append(str(error))

    for root, dirs, filenames in os.walk("F:/", onerror=onerror):
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith((".", "$")) and d != "System Volume Information"
        ]
        for filename in filenames:
            path = Path(root) / filename
            if (
                filename.startswith("._")
                or path.suffix.lower() not in SIGNAL_EXTS
                or str(path) in files
            ):
                continue
            parsed = parse_extended(filename)
            if not parsed:
                continue
            modality, level = classify_file(path)
            if modality == "unknown":
                continue
            try:
                stat = path.stat()
            except OSError as error:
                scan_errors.append(str(error))
                continue
            row = {
                "path": str(path),
                "filename": filename,
                "extension": path.suffix.lower(),
                "bytes": stat.st_size,
                "modified_utc": datetime.fromtimestamp(
                    stat.st_mtime, timezone.utc
                ).isoformat(),
                "modality": modality,
                "source_level": level,
                **parsed,
            }
            discovered.append(row)
            if not row["stage"]:
                unknown.append(row)
            else:
                files[str(path)] = row
    owners = defaultdict(set)
    sessions = defaultdict(set)
    for r in base_links:
        owners[r["path"]].add(r["current_subject_id"])
        sessions[(r["date"], r["recording_code"])].add(r["current_subject_id"])
    alias_owners = defaultdict(set)
    for sid, abbrs in aliases.items():
        for a in abbrs:
            alias_owners[a].add(sid)
    date_alias = defaultdict(set)
    short_stages = defaultdict(set)
    for r in base_links:
        date_alias[(r["date"], r["filename_abbr"])].add(r["current_subject_id"])
    for r in files.values():
        if r.get("parse_rule") == "three_letter_abbreviation_requires_anchor":
            short_stages[(r["date"], r["recording_code"], r["filename_abbr"])].add(
                r["stage"]
            )
    claims = []
    for path, file in files.items():
        if file["stage"] not in allowed_stages:
            continue
        date, number, abbr = file["date"], file["recording_code"], file["filename_abbr"]
        # A known four-letter spelling such as ABCN must not become ABC + N.
        if unphased_known_alias(file, alias_owners, short_stages):
            unknown.append(
                {
                    **file,
                    "stage": "",
                    "parse_rule": "known_unphased_four_letter_abbreviation",
                }
            )
            continue

        def claim(sids, basis, priority, supported):
            for sid in sorted(sids):
                if sid in owners[path]:
                    continue
                claims.append(
                    {
                        **file,
                        "current_subject_id": sid,
                        "subject_name": source_identity_name(by_sid[sid]),
                        "basis": basis,
                        "priority": priority,
                        "supported": supported,
                        "visit_equivalence": "unverified",
                        "rule_version": cfg["version"],
                    }
                )

        exact = {sid for sid in by_code.get(number, set()) if abbr in aliases[sid]}
        if exact:
            claim(exact, "source_code_and_reviewed_alias", 90, True)
        chat = chat_sessions.get((date, number, abbr), set())
        if cfg["allow_exact_name_chat_historical_codes"] and chat:
            claim(chat, "exact_source_name_chat_date_code_abbreviation", 85, True)
        historical = chat_pairs.get((number, abbr), set())
        if cfg.get("allow_confirmed_historical_pair_across_dates") and unique_identity(
            historical, identities
        ):
            claim(
                historical,
                "exact_source_name_chat_confirmed_historical_code_abbreviation_visit_unverified",
                78,
                True,
            )
        if cfg.get("allow_same_date_unique_abbreviation_code_variant"):
            anchored = date_alias.get((date, abbr), set())
            if unique_identity(anchored, identities) and unique_identity(
                alias_owners.get(abbr, set()), identities
            ):
                claim(
                    anchored,
                    "unique_same_date_abbreviation_cross_device_code_variant",
                    82,
                    True,
                )
            missing = chat_date_alias.get((date, abbr), set())
            if not number and unique_identity(missing, identities):
                claim(
                    missing,
                    "missing_code_exact_source_name_chat_date_and_abbreviation",
                    81,
                    True,
                )
        date_code = sessions.get((date, number), set())
        if not abbr and unique_identity(date_code, identities):
            claim(date_code, "missing_abbreviation_unique_date_code_anchor", 80, True)
        near = {
            sid
            for sid in by_code.get(number, set())
            if abbr
            and any(
                levenshtein(abbr, a) <= cfg["same_code_max_abbreviation_distance"]
                for a in aliases[sid]
            )
        }
        if near:
            # Three-letter decoding and typos require a date-session anchor.
            safe_near = near & date_code
            if cfg.get("allow_short_abbreviation_complementary_stages"):
                safe_near |= {
                    sid
                    for sid in near
                    if any(
                        sid in chat_date_alias.get((date, a), set())
                        for a in aliases[sid]
                    )
                }
            claim(
                safe_near, "same_code_abbreviation_variant_same_date_anchor", 80, True
            )
            claim(
                near - safe_near,
                "same_code_abbreviation_variant_without_date_anchor",
                55,
                False,
            )
            stages = short_stages.get((date, number, abbr), set())
            if (
                cfg.get("allow_short_abbreviation_complementary_stages")
                and file.get("parse_rule")
                == "three_letter_abbreviation_requires_anchor"
                and "E" in stages
                and stages & {"N", "C"}
                and unique_identity(near, identities)
            ):
                claim(
                    near,
                    "source_code_reviewed_alias_short_spelling_complementary_E_rest",
                    79,
                    True,
                )
        exact_abbr = alias_owners.get(abbr, set())
        if cfg["allow_unique_abbreviation_historical_candidates"] and unique_identity(
            exact_abbr, identities
        ):
            claim(
                exact_abbr, "unique_abbreviation_other_code_or_missing_code", 50, False
            )
    accepted, review = resolve_claims(claims, identities, owners)
    # Keep a single strongest reason per participant/file; all claims are saved.
    new = {}
    for r in accepted:
        key = r["current_subject_id"], r["path"]
        if key not in new or r["priority"] > new[key]["priority"]:
            new[key] = r
    all_links = [
        {**r, "basis": r["evidence_basis"], "visit_equivalence": "unverified"}
        for r in base_links
    ] + list(new.values())
    accepted_keys = {(r["current_subject_id"], r["path"]) for r in all_links}
    review = [
        r for r in review if (r["current_subject_id"], r["path"]) not in accepted_keys
    ]
    # Candidate coverage excludes competing identities; it is still not accepted.
    candidates = [r for r in review if r["review_reason"] != "identity_conflict"]
    coverage = []
    for sid, subject in by_sid.items():
        before = [r for r in base_links if r["current_subject_id"] == sid]
        supported = [r for r in all_links if r["current_subject_id"] == sid]
        possible = supported + [r for r in candidates if r["current_subject_id"] == sid]
        by_date = defaultdict(list)
        for r in supported:
            by_date[r["date"]].append(r)
        flags = components(supported, ("N", "C"))
        flags_p = components(supported, rest_stages)
        coverage.append(
            {
                "current_subject_id": sid,
                "subject_name": source_identity_name(subject),
                "legacy_code_numeric": subject["legacy_code_numeric"],
                **flags,
                "previous_complete": all(components(before).values()),
                "supported_complete": all(flags.values()),
                "supported_complete_with_P_rest": all(flags_p.values()),
                "electrophysiology_pre_rest_with_P": flags_p[
                    "electrophysiology_pre_rest"
                ],
                "fnirs_pre_rest_with_P": flags_p["fnirs_pre_rest"],
                "P_filled_components": ";".join(
                    k for k in flags if not flags[k] and flags_p[k]
                ),
                "candidate_ceiling_complete": all(components(possible).values()),
                "candidate_ceiling_complete_with_P_rest": all(
                    components(possible, rest_stages).values()
                ),
                "same_date_complete": any(
                    all(components(v).values()) for v in by_date.values()
                ),
                "same_date_complete_with_P_rest": any(
                    all(components(v, rest_stages).values()) for v in by_date.values()
                ),
                "supported_dates": ";".join(sorted(by_date)),
                "missing_supported_components": ";".join(
                    k for k, v in flags.items() if not v
                ),
                "missing_supported_components_with_P": ";".join(
                    k for k, v in flags_p.items() if not v
                ),
                "new_file_links": len(supported) - len(before),
                "visit_to_vas_alignment": "unverified",
            }
        )
    out = (
        ROOT
        / "02_quality_control"
        / f"extended_enc_mapping_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    out.mkdir()

    def save(name, rows):
        fields = list(dict.fromkeys(k for r in rows for k in r)) or ["status"]
        write_csv(out / name, rows, fields)

    save("accepted_subject_to_files_private.csv", all_links)
    save("new_supported_links_private.csv", list(new.values()))
    save("all_candidate_claims_private.csv", claims)
    save("review_candidates_private.csv", review)
    save("new_discovered_files_private.csv", discovered)
    save("unknown_phase_private.csv", unknown)
    save("subject_coverage_private.csv", coverage)
    save(
        "remaining_missing_components_private.csv",
        [r for r in coverage if not r["supported_complete_with_P_rest"]],
    )
    save(
        "P_supplemented_subjects_private.csv",
        [r for r in coverage if r["P_filled_components"]],
    )
    save(
        "identity_aliases_private.csv",
        [
            {
                "current_subject_id": sid,
                "abbreviation": a,
                "sources": ";".join(sorted(alias_sources[(sid, a)])),
            }
            for sid in sorted(aliases)
            for a in sorted(aliases[sid])
        ],
    )
    counts = {
        "subjects": len(subjects),
        "previous_complete": sum(r["previous_complete"] for r in coverage),
        "supported_complete": sum(r["supported_complete"] for r in coverage),
        "supported_complete_with_P_rest": sum(
            r["supported_complete_with_P_rest"] for r in coverage
        ),
        "candidate_ceiling_complete": sum(
            r["candidate_ceiling_complete"] for r in coverage
        ),
        "candidate_ceiling_complete_with_P_rest": sum(
            r["candidate_ceiling_complete_with_P_rest"] for r in coverage
        ),
        "same_date_complete": sum(r["same_date_complete"] for r in coverage),
        "same_date_complete_with_P_rest": sum(
            r["same_date_complete_with_P_rest"] for r in coverage
        ),
        "electrophysiology_complete": sum(
            r["electrophysiology_E"] and r["electrophysiology_pre_rest"]
            for r in coverage
        ),
        "fnirs_complete": sum(r["fnirs_E"] and r["fnirs_pre_rest"] for r in coverage),
        "electrophysiology_complete_with_P_rest": sum(
            r["electrophysiology_E"] and r["electrophysiology_pre_rest_with_P"]
            for r in coverage
        ),
        "fnirs_complete_with_P_rest": sum(
            r["fnirs_E"] and r["fnirs_pre_rest_with_P"] for r in coverage
        ),
        "P_additional_complete_subjects": sum(
            r["supported_complete_with_P_rest"] and not r["supported_complete"]
            for r in coverage
        ),
        "new_supported_file_links": len(new),
        "scan_errors": len(scan_errors),
    }
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    revision = subprocess.run(
        git + ["rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        git + ["status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    used_inputs = [
        manifest_path,
        subjects_path,
        files_path,
        links_path,
        evidence_path,
        chat_path,
        mapping_path,
    ]
    run = {
        "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "status": "file_linkage_only_not_signal_QC_or_visit_alignment",
        "configuration": cfg,
        "configuration_sha256": digest(args.config),
        "inputs": {str(p): digest(p) for p in used_inputs},
        "code_revision": revision,
        "working_tree_dirty": bool(status),
        "code_sha256": {
            str(p): digest(p)
            for p in [
                Path(__file__),
                ROOT / "scripts/build_relaxed_enc_mapping.py",
                ROOT / "scripts/build_enc_signal_inventory.py",
                ROOT / "src/capsaicin/participant_matching.py",
            ]
        },
        "software": {"python": sys.version, "platform": platform.platform()},
        "scan_errors": scan_errors,
        "raw_file_hash_policy": "inventory metadata only; raw signal bytes not consumed for this linkage run",
        "outputs": {p.name: digest(p) for p in out.glob("*.csv")},
    }
    (out / "run_manifest.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "report.md").write_text(
        "# E/N/C 扩展匹配审计\n\n"
        f"P 仅补充静息部分，保留原阶段：含 P 支持四组件齐全 {counts['supported_complete_with_P_rest']}/216，"
        f"其中 P 新增补齐 {counts['P_additional_complete_subjects']} 行。含 P 同日期齐全 {counts['same_date_complete_with_P_rest']} 行。\n\n"
        f"216 行中，原有四组件齐全 {counts['previous_complete']} 行；新增证据后 {counts['supported_complete']} 行。"
        f"纳入未确认候选的可能覆盖上限 {counts['candidate_ceiling_complete']} 行，不可作为已匹配率。\n\n"
        f"电生理 E＋静息 {counts['electrophysiology_complete']} 行；fNIRS E＋静息 {counts['fnirs_complete']} 行。"
        f"四组件在同一日期出现 {counts['same_date_complete']} 行，仍未确认与 VAS 属于同次试验。\n\n"
        "历史编号经源实名、聊天日期、编号、缩写支持后加入身份链接；重复访视不视为等价。"
        "缺阶段文件单列；A/T/B 不纳入，P 不改写成 N/C。候选、冲突和每行缺项见同目录 CSV。源文件及先前输出未改写。\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(out), **counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
