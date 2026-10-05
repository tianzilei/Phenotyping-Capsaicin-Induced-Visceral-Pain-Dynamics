"""Inventory unassigned E/N/C first, then resolve against current missing rows."""

from __future__ import annotations
import argparse
from collections import defaultdict, Counter
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
    read_csv,
    write_csv,
    digest,
    normalize_name,
    source_identity_name,
    vas_signature,
    levenshtein,
    code,
)
from build_enc_signal_inventory import classify_file, SIGNAL_EXTS
from build_extended_enc_mapping import components
from read_legacy_xlsx_audit import xlsx_rows, split_sheets


def parse_reverse(name):
    """Parse explicit phase syntax; ambiguous names require identity evidence."""
    if name.startswith("._"):
        return None
    stem = Path(name).stem
    stem = re.sub(r"acq$", "", stem, flags=re.I)
    token = stem.split("_")[0]
    match = re.fullmatch(r"(20\d{6})(\d{1,3})?([A-Za-z]{3,4}?)([ENC]|NE)", token, re.I)
    if not match:
        # A code-only record has no abbreviation and remains a candidate.
        match = re.fullmatch(r"(20\d{6})(\d{1,3})([ENC])", token, re.I)
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
            and log["actual_date"] == file["date"]
            and log["abbreviation"] in aliases
            and levenshtein(log["abbreviation"], file["filename_abbr"]) <= max_distance
        )
        if short_variant:
            return "source_code_date_log_corroborates_short_abbreviation", log
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
                return "exact_log_participant_source_code_abbreviation", log
    return "", None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-run", type=Path, required=True)
    ap.add_argument("--aliases-run", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=ROOT / "config/reverse_enc_v1.json")
    args = ap.parse_args()
    base = args.base_run.resolve()
    started = datetime.now(timezone.utc).isoformat()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    old_manifest = json.loads((base / "run_manifest.json").read_text(encoding="utf-8"))
    subject_path = next(
        Path(p)
        for p in old_manifest["inputs"]
        if Path(p).name == "capsaicin_baseline_merged_private.csv"
    )
    subjects = {r["current_subject_id"]: r for r in read_csv(subject_path)}
    prior = read_csv(base / "accepted_subject_to_files_private.csv")
    cov = read_csv(base / "subject_coverage_private.csv")
    missing = {r["current_subject_id"]: r for r in cov if r["complete"] == "False"}
    aliases = defaultdict(set)
    alias_path = args.aliases_run / "identity_aliases_private.csv"
    for r in read_csv(alias_path):
        aliases[r["current_subject_id"]].add(r["abbreviation"])
    old_root = next(
        p
        for p in Path("D:/").iterdir()
        if p.name.startswith("capsaicin") and "analysis" not in p.name
    )
    old_people_path = old_root / "data/subject_baseline_info.csv"
    old_people = read_csv(old_people_path)
    canonical = defaultdict(set)
    for sid, s in subjects.items():
        for r in old_people:
            if normalize_name(r.get("Name", "")) == normalize_name(
                source_identity_name(s)
            ) and r.get("name_abbr"):
                canonical[sid].add(r["name_abbr"].upper())
    workbook = next(
        p for p in (old_root / "data/raw").glob("*.xlsx") if p.name.startswith("所有")
    )
    workbook_names = defaultdict(set)
    for _, rows in split_sheets(xlsx_rows(workbook)):
        for r in rows:
            if len(r) > 1 and re.fullmatch(r"[Zz]?\d{1,3}", r[0].strip()):
                workbook_names[code(r[0])].add(normalize_name(r[1]))
    # A stale legacy name can leave canonical empty; reviewed aliases are
    # usable with exact source-workbook identity and independent log metadata.
    for sid, s in subjects.items():
        if (
            not canonical[sid]
            and normalize_name(source_identity_name(s))
            in workbook_names[s["legacy_code_numeric"]]
        ):
            canonical[sid].update(aliases[sid])
    known_paths = {r["path"].lower() for r in prior}
    session_owners = defaultdict(set)
    anchors = defaultdict(set)
    for r in prior:
        session_owners[(r["date"], r["recording_code"], r["filename_abbr"])].add(
            r["current_subject_id"]
        )
        anchors[r["current_subject_id"]].add((r["date"], r["filename_abbr"]))
    roots = [Path("F:/")] + [
        p
        for p in Path("D:/").iterdir()
        if p.is_dir() and (p.name.startswith("Phenotyping") or p == old_root)
    ]
    inventory, logs, errors = [], [], []
    log_paths = []
    scan_files = 0
    for root in roots:
        for folder, dirs, names in os.walk(
            root, onerror=lambda e: errors.append(str(e))
        ):
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith((".", "$"))
                and d
                not in {"System Volume Information", "node_modules", "__pycache__"}
            ]
            for name in names:
                if name.startswith("._"):
                    continue
                path = Path(folder) / name
                if path.suffix.lower() not in SIGNAL_EXTS:
                    continue
                scan_files += 1
                if "lajiaosu" in name.lower() and path.suffix.lower() == ".csv":
                    try:
                        rows = read_csv(path)
                        log_paths.append(path)
                        participants = {
                            r.get("participant", "").strip().upper() for r in rows
                        } - {""}
                        dates = {
                            r.get("date", "")[:10].replace("-", "")
                            for r in rows
                            if re.match(r"\d{4}-\d{2}-\d{2}", r.get("date", ""))
                        }
                        if len(participants) == len(dates) == 1:
                            participant = next(iter(participants))
                            actual = next(iter(dates))
                            parsed = re.fullmatch(
                                r"20\d{6}(\d{1,3})([A-Z]{4})", participant
                            )
                            logs.append(
                                {
                                    "path": str(path),
                                    "participant": participant,
                                    "actual_date": actual,
                                    "recording_code": code(parsed.group(1))
                                    if parsed
                                    else "",
                                    "abbreviation": parsed.group(2) if parsed else "",
                                    "source_sha256": digest(path),
                                    "rows": len(rows),
                                }
                            )
                    except (OSError, ValueError) as e:
                        errors.append(str(e))
                parsed = parse_reverse(name)
                if not parsed:
                    continue
                modality, level = classify_file(path)
                if (
                    modality == "unknown"
                    and path.suffix.lower() == ".csv"
                    and "biopac" in str(path).lower()
                ):
                    modality = "electrophysiology"
                if modality == "unknown":
                    continue
                try:
                    stat = path.stat()
                except OSError as e:
                    errors.append(str(e))
                    continue
                inventory.append(
                    {
                        "path": str(path),
                        "filename": name,
                        "modality": modality,
                        "source_level": level,
                        "bytes": stat.st_size,
                        "modified_utc": datetime.fromtimestamp(
                            stat.st_mtime, timezone.utc
                        ).isoformat(),
                        **parsed,
                    }
                )
    ambiguous = []
    all_aliases = set().union(*aliases.values())
    for r in inventory:
        if (
            r["parse_status"] == "short_abbreviation_ambiguous"
            and r["filename_abbr"] + r["stage"] in all_aliases
        ):
            ambiguous.append(r)
    excluded = {r["path"] for r in ambiguous}
    unassigned = [
        r
        for r in inventory
        if r["path"].lower() not in known_paths and r["path"] not in excluded
    ]
    groups = defaultdict(list)
    for r in unassigned:
        groups[(r["date"], r["recording_code"], r["filename_abbr"])].append(r)
    chats = read_csv(base / "chat_mentions_private.csv")
    dates = defaultdict(set)
    codes = defaultdict(set)
    for r in chats:
        dates[r["current_subject_id"]].add(r["target_date"])
        if r["mentioned_code"]:
            codes[r["current_subject_id"]].add(r["mentioned_code"])
    candidates, summary, new = [], [], []
    for key, files in sorted(groups.items()):
        owners = session_owners.get(key, set())
        group_status = (
            "unlinked_copy_of_assigned_session" if owners else "unassigned_session"
        )
        group_candidates = []
        supported = []
        for sid, s in subjects.items():
            abbrs = aliases[sid] | canonical[sid]
            distance = min((levenshtein(key[2], a) for a in abbrs), default=99)
            same_code = key[1] == s["legacy_code_numeric"]
            near = distance <= cfg["candidate_abbreviation_max_distance"]
            chat_pair = key[0] in dates[sid] and key[1] in codes[sid]
            if not (near or same_code or chat_pair):
                continue
            competing = workbook_names.get(key[1], set()) - {
                normalize_name(source_identity_name(s))
            }
            claims = []
            for f in files:
                basis, log = log_support(
                    f,
                    s,
                    canonical[sid],
                    logs,
                    anchors[sid],
                    cfg["supported_log_abbreviation_max_distance"],
                )
                if basis:
                    claims.append((f, basis, log))
            # Global ownership and multiple current visits are checked before promotion.
            same_name = [
                other
                for other, t in subjects.items()
                if normalize_name(source_identity_name(t))
                == normalize_name(source_identity_name(s))
            ]
            distinct_visits = (
                len({vas_signature(subjects[other]) for other in same_name}) > 1
            )
            can_accept = bool(claims) and not owners and not distinct_visits
            row = {
                "session_date": key[0],
                "recording_code": key[1],
                "filename_abbr": key[2],
                "current_subject_id": sid,
                "subject_name": source_identity_name(s),
                "currently_incomplete": sid in missing,
                "abbreviation_distance": distance,
                "source_code_equal": same_code,
                "chat_date_equal": key[0] in dates[sid],
                "chat_date_code_equal": chat_pair,
                "workbook_other_names": ";".join(sorted(competing)),
                "existing_session_owners": ";".join(sorted(owners)),
                "same_name_multiple_VAS_visits": distinct_visits,
                "log_supported_file_count": len(claims),
                "decision": "supported_pending_global_uniqueness"
                if can_accept
                else "review_only",
                "evidence": ";".join(sorted({b for _, b, _ in claims}))
                or "identifier_similarity_only",
                "missing_components": missing.get(sid, {}).get("missing", ""),
                "available_stages": ";".join(sorted({f["stage"] for f in files})),
            }
            group_candidates.append(row)
            if can_accept:
                supported.append((sid, claims, row))
        if len(supported) == 1:
            sid, claims, row = supported[0]
            row["decision"] = "accepted_log_supported"
            for f, basis, log in claims:
                new.append(
                    {
                        **f,
                        "current_subject_id": sid,
                        "subject_name": source_identity_name(subjects[sid]),
                        "basis": basis,
                        "evidence_log_path": log["path"],
                        "evidence_log_sha256": log["source_sha256"],
                        "filename_date_raw": f["date"],
                        "date": log["actual_date"],
                        "recording_code_raw": f["recording_code"],
                        "recording_code": subjects[sid]["legacy_code_numeric"],
                        "visit_equivalence": "identity_supported_VAS_visit_alignment_not_verified",
                    }
                )
        elif supported:
            for _, _, row in supported:
                row["decision"] = "conflicting_supported_owners_review"
        candidates.extend(group_candidates)
        summary.append(
            {
                "session_date": key[0],
                "recording_code": key[1],
                "filename_abbr": key[2],
                "status": group_status,
                "file_count": len(files),
                "stages": ";".join(sorted({f["stage"] for f in files})),
                "modalities": ";".join(sorted({f["modality"] for f in files})),
                "existing_session_owners": ";".join(sorted(owners)),
                "incomplete_candidate_ids": ";".join(
                    sorted(
                        {
                            r["current_subject_id"]
                            for r in group_candidates
                            if r["currently_incomplete"]
                        }
                    )
                ),
                "accepted_subject_ids": ";".join(
                    sorted(
                        {
                            r["current_subject_id"]
                            for r in group_candidates
                            if r["decision"] == "accepted_log_supported"
                        }
                    )
                ),
            }
        )
    final = prior + new
    coverage = []
    subject_report = []
    for sid, s in subjects.items():
        flags = components(
            [r for r in final if r["current_subject_id"] == sid],
            cfg["coverage_rest_stages"],
        )
        coverage.append(
            {
                "current_subject_id": sid,
                "subject_name": source_identity_name(s),
                **flags,
                "complete": all(flags.values()),
                "missing": ";".join(k for k, v in flags.items() if not v),
            }
        )
        if sid in missing:
            rows = [r for r in candidates if r["current_subject_id"] == sid]
            subject_report.append(
                {
                    "current_subject_id": sid,
                    "subject_name": source_identity_name(s),
                    "missing_before": missing[sid]["missing"],
                    "missing_after": coverage[-1]["missing"],
                    "reverse_candidate_sessions": len(rows),
                    "accepted_file_links": sum(
                        r["current_subject_id"] == sid for r in new
                    ),
                    "candidate_session_keys": ";".join(
                        r["session_date"]
                        + "/"
                        + r["recording_code"]
                        + "/"
                        + r["filename_abbr"]
                        for r in rows
                    ),
                    "result": "new_supported_links"
                    if any(r["current_subject_id"] == sid for r in new)
                    else "review_candidates_only"
                    if rows
                    else "no_orphan_identifier_candidate",
                }
            )
    out = (
        ROOT
        / "02_quality_control"
        / f"reverse_enc_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    out.mkdir()

    def save(name, rows):
        write_csv(
            out / name,
            rows,
            list(dict.fromkeys(k for r in rows for k in r)) or ["status"],
        )

    save("unassigned_enc_files_private.csv", unassigned)
    save("reverse_sessions_private.csv", summary)
    save("ambiguous_unphased_alias_files_private.csv", ambiguous)
    save("reverse_candidates_private.csv", candidates)
    save("new_supported_links_private.csv", new)
    save("psychopy_metadata_private.csv", logs)
    save("remaining_subject_reverse_audit_private.csv", subject_report)
    save("accepted_subject_to_files_private.csv", final)
    save("subject_coverage_private.csv", coverage)
    save(
        "remaining_missing_components_private.csv",
        [r for r in coverage if not r["complete"]],
    )
    counts = {
        "previous_complete": sum(r["complete"] == "True" for r in cov),
        "complete_after": sum(r["complete"] for r in coverage),
        "incomplete_before": len(missing),
        "unassigned_enc_files": len(unassigned),
        "reverse_sessions": len(summary),
        "unassigned_sessions": sum(
            r["status"] == "unassigned_session" for r in summary
        ),
        "incomplete_rows_with_candidates": sum(
            r["reverse_candidate_sessions"] > 0 for r in subject_report
        ),
        "new_supported_file_links": len(new),
        "subjects_with_new_links": len({r["current_subject_id"] for r in new}),
        "psychopy_logs": len(logs),
        "scanned_signal_extension_files": scan_files,
        "scan_errors": len(errors),
    }
    report = [
        "# 未归属 E/N/C 反向匹配",
        "",
        f"未链接文件 {len(unassigned)} 个，按日期/编号/缩写分为 {len(summary)} 组，其中 {counts['unassigned_sessions']} 组没有已知会话归属。",
        "",
        f"原缺项 {len(missing)} 行中 {counts['incomplete_rows_with_candidates']} 行获得候选；新增支持文件 {len(new)} 个，涉及 {counts['subjects_with_new_links']} 行；四组件齐全 {counts['previous_complete']} → {counts['complete_after']}/216。",
        "",
        "新增支持依据来自 PsychoPy participant/date 字段与源编号、姓名缩写和已有记录交叉核验。保留原始文件名日期/编号。P 仅沿用既有静息补充，反向池只含 E/N/C。文件副本不是新增受试者，短缩写不凭单一相似度确认；其余候选不计入支持匹配。",
        "",
        "|受试者行|姓名|候选组数|新增文件|仍缺组件|",
        "|---|---|---|---|---|",
    ]
    for r in subject_report:
        report.append(
            "|"
            + "|".join(
                str(r[k]) or "—"
                for k in [
                    "current_subject_id",
                    "subject_name",
                    "reverse_candidate_sessions",
                    "accepted_file_links",
                    "missing_after",
                ]
            )
            + "|"
        )
    (out / "report_private.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    inputs = [
        args.config,
        subject_path,
        old_people_path,
        workbook,
        alias_path,
        base / "run_manifest.json",
        base / "accepted_subject_to_files_private.csv",
        base / "subject_coverage_private.csv",
        base / "chat_mentions_private.csv",
    ] + log_paths
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    run = {
        "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "configuration": cfg,
        "inputs": {str(p): digest(p) for p in inputs},
        "roots": [str(p) for p in roots],
        "scan_errors": errors,
        "code_revision": subprocess.run(
            git + ["rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip(),
        "working_tree_dirty": bool(
            subprocess.run(
                git + ["status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        ),
        "code_sha256": {
            str(p): digest(p)
            for p in [
                Path(__file__),
                ROOT / "scripts/build_relaxed_enc_mapping.py",
                ROOT / "scripts/build_extended_enc_mapping.py",
                ROOT / "scripts/build_enc_signal_inventory.py",
                ROOT / "scripts/read_legacy_xlsx_audit.py",
                ROOT / "src/capsaicin/participant_matching.py",
            ]
        },
        "software": {"python": sys.version, "platform": platform.platform()},
        "signal_hash_policy": "metadata matching only; no signal values consumed",
        "outputs": {p.name: digest(p) for p in out.iterdir()},
        "inference_performed": False,
    }
    (out / "run_manifest.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(out), **counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
