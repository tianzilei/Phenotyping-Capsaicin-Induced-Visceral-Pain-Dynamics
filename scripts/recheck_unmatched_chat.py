"""Read-only chat/number/date audit; private evidence and narrowly supported fixes."""

from __future__ import annotations
import argparse
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
import json
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
    code,
    levenshtein,
)
from build_extended_enc_mapping import components, parse_extended
from build_enc_signal_inventory import parse_recording_name, classify_file
from capsaicin.participant_matching import infer_target_date, strip_group_suffix


def named_line(line, name):
    """Require an exact participant name immediately after its own numeric code."""
    match = re.search(r"(?:^|[：:\s])([Zz]?\d{1,3})\s*([\u3400-\u9fff·]{2,8})", line)
    if not match or strip_group_suffix(match.group(2)) != name:
        return None
    return code(match.group(1))


def can_correct(
    file, sid, subjects, mentions, accepted, canonical, owners, max_distance
):
    s = subjects[sid]
    name = normalize_name(source_identity_name(s))
    if (
        sum(normalize_name(source_identity_name(x)) == name for x in subjects.values())
        != 1
    ):
        return False
    number, abbr, date = file["recording_code"], file["filename_abbr"], file["date"]
    if not number or abbr not in canonical[sid] or number == s["legacy_code_numeric"]:
        return False
    if levenshtein(number, s["legacy_code_numeric"]) > max_distance:
        return False
    if not any(
        m["current_subject_id"] == sid
        and m["target_date"] == date
        and m["mentioned_code"] == s["legacy_code_numeric"]
        for m in mentions
    ):
        return False
    if not any(
        r["current_subject_id"] == sid
        and r["date"] == date
        and r["filename_abbr"] == abbr
        for r in accepted
    ):
        return False
    return all(
        abbr not in canonical[owner]
        and normalize_name(source_identity_name(subjects[owner])) != name
        for owner in owners
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-run", type=Path, required=True)
    ap.add_argument("--scan", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=ROOT / "config/chat_recheck_v1.json")
    args = ap.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    base = args.base_run.resolve()
    manifest = json.loads((base / "run_manifest.json").read_text(encoding="utf-8"))
    subject_path = next(
        Path(p)
        for p in manifest["inputs"]
        if Path(p).name == "capsaicin_baseline_merged_private.csv"
    )
    chat_path = next((ROOT / "00_protocol").glob("*.json"))
    chat = json.loads(chat_path.read_text(encoding="utf-8-sig"))["messages"]
    subjects = {r["current_subject_id"]: r for r in read_csv(subject_path)}
    missing = read_csv(base / "remaining_missing_components_private.csv")
    prior = read_csv(base / "accepted_subject_to_files_private.csv")
    aliases = defaultdict(set)
    for r in read_csv(base / "identity_aliases_private.csv"):
        aliases[r["current_subject_id"]].add(r["abbreviation"])
    old_path = (
        next(
            p
            for p in Path("D:/").iterdir()
            if p.name.startswith("capsaicin") and "analysis" not in p.name
        )
        / "data/subject_baseline_info.csv"
    )
    old = read_csv(old_path)
    canonical = defaultdict(set)
    for sid, s in subjects.items():
        for r in old:
            if normalize_name(r.get("Name", "")) == normalize_name(
                source_identity_name(s)
            ) and r.get("name_abbr"):
                canonical[sid].add(r["name_abbr"].upper())
    # Process chronologically, while preserving the export index and nonunique local ID.
    ordered = sorted(enumerate(chat), key=lambda x: (int(x[1]["createTime"]), x[0]))
    mentions, contexts, name_variants = [], [], []
    previous_date = previous_time = None
    for index, msg in ordered:
        content = str(msg.get("content") or "")
        dt = datetime.fromtimestamp(
            int(msg["createTime"]), timezone(timedelta(hours=8))
        )
        target, basis = infer_target_date(content, dt, previous_date, previous_time)
        if re.search(r"[Zz]?\d{3}\s*[\u3400-\u9fff]", content):
            previous_date, previous_time = target, dt
        for s in missing:
            sid, name = s["current_subject_id"], normalize_name(s["subject_name"])
            if name not in content:
                for no, line in enumerate(content.splitlines(), 1):
                    match = re.search(
                        r"(?:^|[：:\s])([Zz]?\d{1,3})\s*([\u3400-\u9fff·]{2,8})", line
                    )
                    if match:
                        variant = strip_group_suffix(match.group(2))
                        if (
                            len(name) >= 3
                            and len(variant) == len(name)
                            and levenshtein(name, variant) == 1
                        ):
                            name_variants.append(
                                {
                                    "current_subject_id": sid,
                                    "source_name": name,
                                    "chat_name": variant,
                                    "mentioned_code": code(match.group(1)),
                                    "target_date": target.strftime("%Y%m%d"),
                                    "message_index": index,
                                    "message_time": dt.isoformat(),
                                    "line_number": no,
                                    "line": line,
                                    "status": "spelling_candidate_not_identity_confirmation",
                                }
                            )
                continue
            key = f"message_{index:04d}_{msg['createTime']}_{msg.get('localId', '')}"
            for no, line in enumerate(content.splitlines(), 1):
                if name not in line:
                    continue
                number = named_line(line, name)
                mentions.append(
                    {
                        "current_subject_id": sid,
                        "subject_name": name,
                        "message_key": key,
                        "message_time": dt.isoformat(),
                        "target_date": target.strftime("%Y%m%d"),
                        "date_basis": basis,
                        "mentioned_code": number or "",
                        "line_number": no,
                        "date_status": "correction_without_explicit_date_review_context"
                        if "更正" in content and not re.search(r"\d+月\d+", content)
                        else "schedule_date_not_completed_visit",
                        "line": line,
                        "is_correction": any(w in content for w in ["更正", "调整"]),
                        "reservation": "预" in line,
                        "match_type": "exact_name_with_code"
                        if number
                        else "name_text_only",
                    }
                )
            contexts.append(
                {
                    "current_subject_id": sid,
                    "message_key": key,
                    "content": content,
                    "previous_message": str(chat[index - 1].get("content") or "")
                    if index
                    else "",
                    "next_message": str(chat[index + 1].get("content") or "")
                    if index + 1 < len(chat)
                    else "",
                }
            )
    scan = json.loads(args.scan.read_text(encoding="utf-8"))
    inventory = []
    for raw in scan["paths"]:
        p = Path(raw)
        if p.name.startswith("._"):
            continue
        parsed = parse_recording_name(p.name)
        if parsed and not parsed["phase"]:
            parsed = None
        parsed = parsed or parse_extended(p.name)
        if not parsed:
            continue
        modality, level = classify_file(p)
        # Split exports in the legacy analysis tree also carry signal data.
        if (
            p.suffix.lower() == ".csv"
            and "biopac" in str(p).lower()
            and modality == "unknown"
        ):
            modality, level = "electrophysiology", "legacy_split_csv"
        if modality == "unknown":
            continue
        inventory.append(
            {
                "path": raw,
                "filename": p.name,
                "date": parsed["date"],
                "recording_code": parsed["recording_code"],
                "filename_abbr": parsed["filename_abbr"],
                "stage": parsed.get("phase") or parsed.get("stage", ""),
                "modality": modality,
                "source_level": level,
                "bytes": p.stat().st_size,
            }
        )
    owners = defaultdict(set)
    for r in prior:
        owners[r["path"]].add(r["current_subject_id"])
    corrections, candidates, summaries = [], [], []
    replacements = {}
    for s in missing:
        sid = s["current_subject_id"]
        subject = subjects[sid]
        name = normalize_name(s["subject_name"])
        own_mentions = [m for m in mentions if m["current_subject_id"] == sid]
        codes = {m["mentioned_code"] for m in own_mentions if m["mentioned_code"]} | {
            s["legacy_code_numeric"]
        }
        dates = {m["target_date"] for m in own_mentions}
        own_files = []
        same_name_rows = [
            r
            for other, r in subjects.items()
            if other != sid and normalize_name(source_identity_name(r)) == name
        ]
        for f in inventory:
            abbr_hit = f["filename_abbr"] in aliases[sid] | canonical[sid]
            date_code_hit = f["date"] in dates and f["recording_code"] in codes
            if not abbr_hit and not date_code_hit:
                continue
            row = {
                **f,
                "current_subject_id": sid,
                "subject_name": name,
                "chat_date_match": f["date"] in dates,
                "chat_code_match": f["recording_code"] in codes,
                "abbreviation_match": abbr_hit,
                "current_file_owners": ";".join(sorted(owners[f["path"]])),
                "existing_link": sid in owners[f["path"]],
            }
            own_files.append(row)
            if f["stage"] in {"E", "N", "C", "P"} and can_correct(
                f,
                sid,
                subjects,
                mentions,
                prior,
                canonical,
                owners[f["path"]],
                cfg["date_code_correction_max_edit_distance"],
            ):
                correction = {
                    **row,
                    "basis": "exact_chat_date_source_name_cross_device_code_typo",
                    "corrected_subject_id": sid,
                    "previous_owner_ids": ";".join(sorted(owners[f["path"]])),
                    "chat_message_keys": ";".join(
                        sorted(
                            {
                                m["message_key"]
                                for m in own_mentions
                                if m["target_date"] == f["date"]
                            }
                        )
                    ),
                }
                corrections.append(correction)
                replacements[f["path"]] = correction
        candidates.extend(own_files)
        summaries.append(
            {
                "current_subject_id": sid,
                "subject_name": name,
                "source_code": s["legacy_code_numeric"],
                "missing_before": s["missing_supported_components_with_P"],
                "chat_message_count": len({m["message_key"] for m in own_mentions}),
                "chat_codes": ";".join(sorted(codes, key=int)),
                "chat_trial_dates": ";".join(sorted(dates)),
                "chat_correction_message_count": len(
                    {m["message_key"] for m in own_mentions if m["is_correction"]}
                ),
                "existing_supported_dates": s["supported_dates"],
                "same_name_other_rows": ";".join(
                    r["current_subject_id"] + ":" + r["legacy_code_numeric"]
                    for r in same_name_rows
                ),
                "same_name_different_VAS_rows": ";".join(
                    r["current_subject_id"]
                    for r in same_name_rows
                    if vas_signature(r) != vas_signature(subject)
                ),
                "found_signal_file_count": len(own_files),
                "observed_file_stages": ";".join(
                    sorted({r["stage"] for r in own_files})
                ),
                "historical_E_files_with_other_owner": len(
                    {
                        r["path"]
                        for r in own_files
                        if r["stage"] == "E"
                        and r["abbreviation_match"]
                        and r["current_file_owners"]
                        and not r["existing_link"]
                    }
                ),
                "chat_search_status": "exact_name_found"
                if own_mentions
                else "no_exact_name_in_available_export_not_absence_of_participation",
            }
        )
    final = [r for r in prior if r["path"] not in replacements]
    final += [
        {
            **r,
            "current_subject_id": r["corrected_subject_id"],
            "visit_equivalence": "unverified",
        }
        for r in replacements.values()
    ]
    coverage = []
    for sid, s in subjects.items():
        rows = [r for r in final if r["current_subject_id"] == sid]
        flags = components(rows, cfg["rest_stages"])
        coverage.append(
            {
                "current_subject_id": sid,
                "subject_name": source_identity_name(s),
                **flags,
                "complete": all(flags.values()),
                "missing": ";".join(k for k, v in flags.items() if not v),
            }
        )
    cov = {r["current_subject_id"]: r for r in coverage}
    for s in summaries:
        s["missing_after"] = cov[s["current_subject_id"]]["missing"]
        s["complete_after"] = cov[s["current_subject_id"]]["complete"]
        s["supported_code_corrections"] = sum(
            r["current_subject_id"] == s["current_subject_id"] for r in corrections
        )
        s["one_character_name_candidate_count"] = sum(
            r["current_subject_id"] == s["current_subject_id"] for r in name_variants
        )
        s["conclusion"] = (
            "聊天同日源编号、姓名缩写与已匹配另一设备一致；纠正漏写编号后补齐"
            if s["complete_after"]
            else "当前聊天导出未覆盖该姓名；保留已有文件日期，需追溯较早记录或姓名变体"
            if not s["chat_message_count"]
            else "已追出历史编号；同名其他行VAS不同，旧E记录不能直接视为本行同次试验"
            if s["same_name_different_VAS_rows"]
            else "存在其他归属的同缩写E文件，保留冲突，需原始记录确认编号"
            if s["historical_E_files_with_other_owner"]
            else "聊天编号与日期已列明，现存文件仍未覆盖缺失E段；需检查漏命名、合并记录或原始备份"
        )
    out = (
        ROOT
        / "02_quality_control"
        / f"chat_unmatched_recheck_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    out.mkdir()

    def save(name, rows):
        write_csv(
            out / name,
            rows,
            list(dict.fromkeys(k for r in rows for k in r)) or ["status"],
        )

    save("subject_chat_date_number_audit_private.csv", summaries)
    save("chat_mentions_private.csv", mentions)
    save("chat_contexts_private.csv", contexts)
    save("one_character_name_candidates_private.csv", name_variants)
    save("signal_candidates_private.csv", candidates)
    save("supported_number_corrections_private.csv", corrections)
    save("accepted_subject_to_files_private.csv", final)
    save("subject_coverage_private.csv", coverage)
    counts = {
        "reviewed_rows": len(missing),
        "rows_with_exact_name_chat": sum(
            s["chat_message_count"] > 0 for s in summaries
        ),
        "rows_without_exact_name_chat": sum(
            s["chat_message_count"] == 0 for s in summaries
        ),
        "complete_after": sum(r["complete"] for r in coverage),
        "corrected_file_links": len(corrections),
        "corrected_subject_rows": len({r["current_subject_id"] for r in corrections}),
    }
    report = [
        "# 未匹配受试者聊天核查",
        "",
        f"核查 {len(missing)} 行；{counts['rows_with_exact_name_chat']} 行有精确姓名聊天，{counts['rows_without_exact_name_chat']} 行未在当前导出命中。",
        "",
        "当前导出从 2025-03-24 开始，无法覆盖 2024 年原始试验。聊天日期是安排日期，保留原文和推断依据；不自动代表完成采集。",
        "",
        f"本轮直接证据纠正 {len(corrections)} 条文件链接，涉及 {counts['corrected_subject_rows']} 行；双模态 E＋N/C/P 齐全 {counts['complete_after']}/216。",
        "",
        "P 仅补静息，A/T/B 保留为其他阶段线索。同名但 VAS 不同的历史行不自动合并。",
        "",
        "已发现聊天中的编号更正和安排修订。每条原文、消息时间和上下文均在聊天证据表中。消息 localId 在导出中重复，因此同时保存导出索引和时间戳。",
        "",
        "待核实线索包括日期与编号粘连/缺字，以及同日重复C或N文件。当前保留原阶段，不把较晚记录自动改作E。",
        "",
        "|当前行|源编号|姓名|聊天编号|聊天日期|原有文件日期|仍缺组件|核查结论|",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        report.append(
            "|"
            + "|".join(
                str(s[k]) or "—"
                for k in [
                    "current_subject_id",
                    "source_code",
                    "subject_name",
                    "chat_codes",
                    "chat_trial_dates",
                    "existing_supported_dates",
                    "missing_after",
                    "conclusion",
                ]
            )
            + "|"
        )
    (out / "report_private.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    inputs = [
        subject_path,
        chat_path,
        old_path,
        args.scan,
        args.config,
        base / "run_manifest.json",
        base / "identity_aliases_private.csv",
        base / "accepted_subject_to_files_private.csv",
        base / "remaining_missing_components_private.csv",
    ]
    run = {
        "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "configuration": cfg,
        "inputs": {str(p): digest(p) for p in inputs},
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
                ROOT / "scripts/build_extended_enc_mapping.py",
                ROOT / "scripts/build_relaxed_enc_mapping.py",
                ROOT / "scripts/build_enc_signal_inventory.py",
                ROOT / "src/capsaicin/participant_matching.py",
            ]
        },
        "software": {"python": sys.version, "platform": platform.platform()},
        "scan_roots": "F and two D-drive research project trees; metadata only",
        "scan_errors": scan["errors"],
        "outputs": {p.name: digest(p) for p in out.iterdir()},
        "inference_performed": False,
    }
    (out / "run_manifest.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(out), **counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
