"""Time-led audit of orphan E/N/C; no identity assignment from time alone."""

from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
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
)
from build_extended_enc_mapping import components


def filename_time(name):
    m = re.search(r"_(20\d{6})_(\d{6})(?:\D|$)", name)
    if not m:
        return None
    try:
        return datetime.strptime("".join(m.groups()), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def log_interval(rows):
    starts = {r.get("expStart", "") for r in rows} - {""}
    if len(starts) != 1:
        return None
    raw = next(iter(starts))
    try:
        start = datetime.strptime(raw.split(" +")[0], "%Y-%m-%d %Hh%M.%S.%f")
    except ValueError:
        return None
    elapsed = []
    for row in rows:
        for key, v in row.items():
            if key.endswith((".started", ".stopped")):
                try:
                    value = float(v)
                except (ValueError, TypeError):
                    continue
                if math.isfinite(value) and value >= 0:
                    elapsed.append(value)
    return (start, start + timedelta(seconds=max(elapsed))) if elapsed else None


def interval_gap(time, interval):
    if interval[0] <= time <= interval[1]:
        return 0.0
    return min(
        abs((time - interval[0]).total_seconds()),
        abs((time - interval[1]).total_seconds()),
    )


def supported_time_match(
    chat_code, rest_anchor, own_intervals, competing_intervals, time, padding
):
    return bool(
        chat_code
        and rest_anchor
        and own_intervals
        and any(interval_gap(time, x) <= padding for x in own_intervals)
        and not any(interval_gap(time, x) <= padding for x in competing_intervals)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-run", type=Path, required=True)
    ap.add_argument("--chat-run", type=Path, required=True)
    ap.add_argument("--aliases-run", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=ROOT / "config/time_linkage_v1.json")
    args = ap.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    base = args.base_run
    m = json.loads((base / "run_manifest.json").read_text(encoding="utf-8"))
    subject_path = next(
        Path(p)
        for p in m["inputs"]
        if Path(p).name == "capsaicin_baseline_merged_private.csv"
    )
    subjects = {r["current_subject_id"]: r for r in read_csv(subject_path)}
    prior = read_csv(base / "accepted_subject_to_files_private.csv")
    used = {r["path"].lower() for r in prior}
    files = [
        r
        for r in read_csv(base / "unassigned_enc_files_private.csv")
        if r["path"].lower() not in used
    ]
    coverage = read_csv(base / "subject_coverage_private.csv")
    missing = {r["current_subject_id"]: r for r in coverage if r["complete"] == "False"}
    chats = read_csv(args.chat_run / "chat_mentions_private.csv")
    aliases = defaultdict(set)
    for r in read_csv(args.aliases_run / "identity_aliases_private.csv"):
        aliases[r["current_subject_id"]].add(r["abbreviation"])
    # Logs are checked against all source identities, not just incomplete rows.
    logs = []
    log_sources = []
    for log in read_csv(base / "psychopy_metadata_private.csv"):
        path = Path(log["path"])
        rows = read_csv(path)
        log_sources.append(path)
        interval = log_interval(rows)
        if not interval:
            continue
        match = re.search(r"([A-Z]{4})$", log["participant"])
        abbr = match.group(1) if match else ""
        owners = {sid for sid in subjects if abbr in aliases[sid]}
        names = {normalize_name(source_identity_name(subjects[sid])) for sid in owners}
        logs.append(
            {
                **log,
                "abbreviation_resolved": abbr,
                "start": interval[0],
                "end": interval[1],
                "candidate_owners": owners,
                "unique_name": len(names) == 1,
            }
        )
    groups = defaultdict(list)
    for r in files:
        groups[(r["date"], r["recording_code"], r["filename_abbr"])].append(r)
    timestamps = []
    candidates = []
    proposals = []
    sessions = []
    header_inputs = []
    for key, rows in sorted(groups.items()):
        clocks = []
        for r in rows:
            t = filename_time(r["filename"])
            if t:
                clocks.append((t, r["stage"]))
                timestamps.append(
                    {
                        "path": r["path"],
                        "timestamp": t.isoformat(),
                        "basis": "embedded_filename_device_timestamp",
                        "header_sha256": "",
                    }
                )
            if Path(r["path"]).suffix.lower() in {".txt", ".csv"}:
                with Path(r["path"]).open("rb") as f:
                    raw = f.read(cfg["header_read_bytes"])
                text = raw.decode("utf-8-sig", errors="replace")
                h = re.search(
                    r"(?:Measured Date|^Date)[\t, ]+(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})",
                    text,
                    re.M,
                )
                header_inputs.append(
                    {
                        "path": r["path"],
                        "bytes_read": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                )
                if h:
                    t = datetime.strptime(h.group(1), "%Y/%m/%d %H:%M:%S")
                    clocks.append((t, r["stage"]))
                    timestamps.append(
                        {
                            "path": r["path"],
                            "timestamp": t.isoformat(),
                            "basis": "measured_date_header",
                            "header_sha256": hashlib.sha256(raw).hexdigest(),
                        }
                    )
        actual_dates = {t.strftime("%Y%m%d") for t, _ in clocks} | {key[0]}
        dates_for_compare = [datetime.strptime(d, "%Y%m%d") for d in actual_dates]
        session_rows = []
        for sid, gap in missing.items():
            mentions = [c for c in chats if c["current_subject_id"] == sid]
            own_logs = [
                l for l in logs if sid in l["candidate_owners"] and l["unique_name"]
            ]
            anchors = [
                r
                for r in prior
                if r["current_subject_id"] == sid and r["stage"] in {"E", "N", "C"}
            ]
            sources = [
                (c["target_date"], "chat", c.get("message_key", "")) for c in mentions
            ]
            sources += [(l["actual_date"], "psychopy", l["path"]) for l in own_logs]
            sources += [(r["date"], "accepted_record", r["path"]) for r in anchors]
            if not sources:
                continue
            distances = [
                (
                    min(
                        abs((datetime.strptime(d, "%Y%m%d") - fd).days)
                        for fd in dates_for_compare
                    ),
                    kind,
                    ref,
                    d,
                )
                for d, kind, ref in sources
            ]
            nearest = min(x[0] for x in distances)
            if nearest > max(cfg["candidate_date_offsets_days"]):
                continue
            same_chat = [c for c in mentions if c["target_date"] in actual_dates]
            code_chat = [
                c
                for c in same_chat
                if c["mentioned_code"] == key[1]
                and c["match_type"] == "exact_name_with_code"
            ]
            rest_anchors = [
                r
                for r in anchors
                if r["stage"] in {"N", "C"}
                and r["recording_code"] == key[1]
                and r["date"] in actual_dates
            ]
            anchor_times = [filename_time(r["filename"]) for r in rest_anchors]
            anchor_times = [t for t in anchor_times if t]
            own_intervals = [
                (l["start"], l["end"])
                for l in own_logs
                if l["actual_date"] in actual_dates
            ]
            competing = [
                (l["start"], l["end"])
                for l in logs
                if l["actual_date"] in actual_dates and sid not in l["candidate_owners"]
            ]
            good = []
            for t, stage in clocks:
                anchor_ok = any(
                    0
                    <= (t - a).total_seconds()
                    <= cfg["same_session_anchor_max_seconds"]
                    for a in anchor_times
                )
                if stage == "E" and supported_time_match(
                    bool(code_chat),
                    anchor_ok,
                    own_intervals,
                    competing,
                    t,
                    cfg["log_interval_padding_seconds"],
                ):
                    good.append(t)
            identities = {
                normalize_name(source_identity_name(s))
                for s in subjects.values()
                if s["current_subject_id"]
                in {l_sid for l in own_logs for l_sid in l["candidate_owners"]}
            }
            matched_stages = {r["stage"] for r in rows}
            fills = any(
                (
                    r["modality"].startswith("electrophysiology")
                    and (
                        "electrophysiology_E"
                        if r["stage"] == "E"
                        else "electrophysiology_pre_rest"
                    )
                    in gap["missing"]
                )
                or (
                    r["modality"] == "fnirs"
                    and ("fnirs_E" if r["stage"] == "E" else "fnirs_pre_rest")
                    in gap["missing"]
                )
                for r in rows
            )
            row = {
                "date": key[0],
                "recording_code": key[1],
                "filename_abbr": key[2],
                "current_subject_id": sid,
                "subject_name": gap["subject_name"],
                "nearest_date_gap_days": nearest,
                "same_date_chat_messages": ";".join(
                    sorted({c["message_key"] for c in same_chat})
                ),
                "same_date_same_code_chat_messages": ";".join(
                    sorted({c["message_key"] for c in code_chat})
                ),
                "timestamp_values": ";".join(
                    sorted({t.isoformat() for t, _ in clocks})
                ),
                "own_log_intervals": ";".join(
                    a.isoformat() + "/" + b.isoformat() for a, b in own_intervals
                ),
                "competing_log_intervals": ";".join(
                    a.isoformat() + "/" + b.isoformat() for a, b in competing
                ),
                "rest_anchor_count": len(rest_anchors),
                "fills_missing_component": fills,
                "minimum_log_gap_seconds": min(
                    (interval_gap(t, i) for t, _ in clocks for i in own_intervals),
                    default="",
                ),
                "nearest_evidence_refs": ";".join(
                    sorted({x[2] for x in distances if x[0] == nearest})
                ),
                "decision": "supported_pending_unique_owner"
                if good and len(identities) == 1 and fills
                else "time_candidate_only",
            }
            session_rows.append(row)
            if row["decision"] == "supported_pending_unique_owner":
                proposals.append((key, sid, row))
        candidates += session_rows
        sessions.append(
            {
                "date": key[0],
                "recording_code": key[1],
                "filename_abbr": key[2],
                "file_count": len(rows),
                "stages": ";".join(sorted({r["stage"] for r in rows})),
                "same_day_candidate_ids": ";".join(
                    sorted(
                        {
                            r["current_subject_id"]
                            for r in session_rows
                            if r["nearest_date_gap_days"] == 0
                        }
                    )
                ),
                "three_day_candidate_ids": ";".join(
                    sorted({r["current_subject_id"] for r in session_rows})
                ),
                "has_clock_timestamp": bool(clocks),
            }
        )
    proposal_by_key = defaultdict(list)
    for key, sid, row in proposals:
        proposal_by_key[key].append((sid, row))
    new = []
    for key, rows in proposal_by_key.items():
        if len(rows) != 1:
            for _, r in rows:
                r["decision"] = "competing_subjects_review"
            continue
        sid, claim = rows[0]
        claim["decision"] = "accepted_chat_log_clock_rest_anchor"
        for f in groups[key]:
            if f["stage"] != "E":
                continue
            new.append(
                {
                    **f,
                    "current_subject_id": sid,
                    "subject_name": missing[sid]["subject_name"],
                    "basis": claim["decision"],
                    "chat_message_keys": claim["same_date_same_code_chat_messages"],
                    "log_interval_evidence": claim["own_log_intervals"],
                    "device_timestamps": claim["timestamp_values"],
                    "visit_equivalence": "identity_supported_VAS_visit_alignment_unverified",
                }
            )
    final = prior + new
    new_cov = []
    subject_summary = []
    for sid, s in subjects.items():
        flags = components(
            [r for r in final if r["current_subject_id"] == sid],
            cfg["coverage_rest_stages"],
        )
        new_cov.append(
            {
                "current_subject_id": sid,
                "subject_name": source_identity_name(s),
                **flags,
                "complete": all(flags.values()),
                "missing": ";".join(k for k, v in flags.items() if not v),
            }
        )
        if sid in missing:
            c = [r for r in candidates if r["current_subject_id"] == sid]
            subject_summary.append(
                {
                    "current_subject_id": sid,
                    "subject_name": missing[sid]["subject_name"],
                    "missing_before": missing[sid]["missing"],
                    "missing_after": new_cov[-1]["missing"],
                    "same_day_groups": sum(r["nearest_date_gap_days"] == 0 for r in c),
                    "within_one_day_groups": sum(
                        r["nearest_date_gap_days"] <= 1 for r in c
                    ),
                    "within_three_day_groups": len(c),
                    "new_files": sum(r["current_subject_id"] == sid for r in new),
                }
            )
    out = (
        ROOT
        / "02_quality_control"
        / f"time_enc_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    out.mkdir()

    def save(name, rows):
        write_csv(
            out / name,
            rows,
            list(dict.fromkeys(k for r in rows for k in r)) or ["status"],
        )

    save("time_candidates_private.csv", candidates)
    save("device_timestamps_private.csv", timestamps)
    save("header_hashes_private.csv", header_inputs)
    save("remaining_orphan_sessions_private.csv", sessions)
    save("subject_time_audit_private.csv", subject_summary)
    save("new_supported_links_private.csv", new)
    save("accepted_subject_to_files_private.csv", final)
    save("subject_coverage_private.csv", new_cov)
    save(
        "remaining_missing_components_private.csv",
        [r for r in new_cov if not r["complete"]],
    )
    counts = {
        "orphan_files_after_prior_assignments": len(files),
        "orphan_groups": len(groups),
        "incomplete_before": len(missing),
        "subjects_same_day_candidates": sum(
            r["same_day_groups"] > 0 for r in subject_summary
        ),
        "subjects_within_three_day_candidates": sum(
            r["within_three_day_groups"] > 0 for r in subject_summary
        ),
        "new_supported_files": len(new),
        "complete_before": sum(r["complete"] == "True" for r in coverage),
        "complete_after": sum(r["complete"] for r in new_cov),
    }
    report = [
        "# 聊天与设备时间交叉匹配",
        "",
        f"此前601个文件中已有11个在上一轮获配，本轮检查剩余{len(files)}个文件、{len(groups)}个日期/编号/缩写组。",
        "",
        f"35个缺项行中，同日有候选{counts['subjects_same_day_candidates']}行，扩大到±3日有候选{counts['subjects_within_three_day_candidates']}行。新增支持文件{len(new)}个，齐全率{counts['complete_before']}→{counts['complete_after']}/216。",
        "",
        "同一天或前后几天只产生候选。支持链接还要求同日精确姓名聊天编号、已确认的同编号静息文件时间、该身份的PsychoPy时间区间及无竞争日志。设备记录/保存时间允许5分钟边界误差，不代表信号已同步。A/T/B不补E，P仅沿用静息补充。",
        "",
        "|当前行|姓名|同日候选组|±3日候选组|新增文件|仍缺|",
        "|---|---|---|---|---|---|",
    ]
    for r in subject_summary:
        report.append(
            "|"
            + "|".join(
                str(r[k]) or "—"
                for k in [
                    "current_subject_id",
                    "subject_name",
                    "same_day_groups",
                    "within_three_day_groups",
                    "new_files",
                    "missing_after",
                ]
            )
            + "|"
        )
    (out / "report_private.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    inputs = (
        [
            args.config,
            subject_path,
            args.chat_run / "chat_mentions_private.csv",
            args.aliases_run / "identity_aliases_private.csv",
        ]
        + [
            base / n
            for n in [
                "run_manifest.json",
                "accepted_subject_to_files_private.csv",
                "subject_coverage_private.csv",
                "unassigned_enc_files_private.csv",
                "psychopy_metadata_private.csv",
            ]
        ]
        + log_sources
    )
    manifest = {
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
                ROOT / "scripts/build_relaxed_enc_mapping.py",
                ROOT / "scripts/build_extended_enc_mapping.py",
                ROOT / "src/capsaicin/participant_matching.py",
            ]
        },
        "software": {"python": sys.version, "platform": platform.platform()},
        "outputs": {p.name: digest(p) for p in out.iterdir()},
        "inference_performed": False,
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(out), **counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
