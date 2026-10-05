"""Algorithmic minute-scale fNIRS ROI analysis for the variable-length VAS cohort."""

import csv
import json
import hashlib
import platform
import subprocess
import uuid
import math
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from path_resolver import resolve_external_path, execution_config
from capsaicin.data_locations import resolve_input, relocation_evidence
from capsaicin.fnirs_source_selection import adjudicate_mapping

CFG = ROOT / "config/fnirs_variable_length_roi_v1.json"
VAS = (
    ROOT
    / "01_data/processed/e_coded_20260916T144438Z_5c144eb7/BaselineData_E_coded.csv"
)
MAP = (
    ROOT
    / "02_quality_control/time_enc_20260916T123124Z_d4ff4af0/accepted_subject_to_files_private.csv"
)
ROI = ROOT / "00_protocol/acquisition_qc_20260919/data/16_fnirs_channel_qc.csv"


def read(p):
    with Path(p).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def write(p, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with Path(p).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except:
        return None


def parse_channel_groups(channel_line):
    """Parse Shimadzu header: four metadata fields, then HbO/HbR/HbT triplets."""
    labels = []
    for h in channel_line[4:]:
        m = "".join(c for c in h if c.isdigit())
        labels.append("ch-" + str(int(m)) if m else "")
    if len(labels) % 3:
        raise ValueError("channel_header_not_triplet_aligned")
    groups = []
    for k in range(0, len(labels), 3):
        triplet = labels[k : k + 3]
        if not triplet[0] or triplet != [triplet[0]] * 3:
            raise ValueError("channel_triplet_mismatch")
        groups.append((triplet[0], 4 + k))
    return groups


def fixed_beta(rows, key):
    if not rows:
        return None
    y = np.array([r["vas_mean"] for r in rows], float)
    x = np.array([r[key] for r in rows], float)
    s = [r["subject_id"] for r in rows]
    w = [r["block"] for r in rows]
    cols = [np.ones(len(rows))]
    for v in sorted(set(s))[1:]:
        cols.append(np.array([z == v for z in s], float))
    for v in sorted(set(w))[1:]:
        cols.append(np.array([z == v for z in w], float))
    Z = np.column_stack(cols)
    ry = y - Z @ np.linalg.lstsq(Z, y, rcond=None)[0]
    rx = x - Z @ np.linalg.lstsq(Z, x, rcond=None)[0]
    return float(rx @ ry / (rx @ rx)) if rx @ rx > 1e-12 else None


def bootstrap(rows, key, B=2000, seed=20260921):
    rng = np.random.default_rng(seed)
    ids = sorted({r["subject_id"] for r in rows})
    vals = []
    for _ in range(B):
        take = rng.choice(ids, len(ids), replace=True)
        s = [r for i in take for r in rows if r["subject_id"] == i]
        b = fixed_beta(s, key)
        if b is not None:
            vals.append(b)
    return {
        "n_bootstrap": len(vals),
        "beta_low": float(np.quantile(vals, 0.025)) if vals else None,
        "beta_median": float(np.median(vals)) if vals else None,
        "beta_high": float(np.quantile(vals, 0.975)) if vals else None,
    }


def main():
    global CFG, VAS, MAP, ROI
    CFG = execution_config(CFG)
    VAS = resolve_input(VAS)
    MAP = resolve_input(MAP)
    ROI = resolve_input(ROI)
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    vas = {r["ID"]: r for r in read(VAS)}
    # Confirmed ROI mapping is repeated per record/window; use the modal nonblank label per channel.
    roi_rows = read(ROI)
    ch_roi = {}
    for r in roi_rows:
        ch = r["channel_id"]
        label = r.get("roi_label", "").strip()
        if label:
            ch_roi.setdefault(ch, Counter())[label] += 1
    ch_roi = {k: v.most_common(1)[0][0] for k, v in ch_roi.items() if v}
    mapping = [
        r
        for r in read(MAP)
        if r.get("stage") == "E"
        and r.get("extension", "").lower() == ".txt"
        and not Path(r["path"]).name.startswith("._")
        and r.get("current_subject_id") in vas
    ]
    mapping, source_decisions, decision_evidence = adjudicate_mapping(mapping)
    # Resolve the verified D: alias and retain one canonical path per subject. A same-hash
    # pair is an export duplicate; different-hash pairs remain unresolved and
    # are excluded from estimators pending record identity adjudication.
    by_subject = defaultdict(list)
    for r in mapping:
        p = resolve_external_path(r["path"])
        if p is not None:
            q = dict(r)
            q["_resolved"] = str(p)
            q["_hash"] = sha(p)
            by_subject[r["current_subject_id"]].append(q)
    canonical = []
    unresolved_subjects = []
    for sid, rs in by_subject.items():
        hashes = {r["_hash"] for r in rs}
        if len(hashes) == 1:
            canonical.append(rs[0])
        elif len(rs) == 1:
            canonical.append(rs[0])
        else:
            unresolved_subjects.append(sid)
    files = [(r["_resolved"], r) for r in canonical]
    out = (
        ROOT
        / "08_outputs"
        / (
            "fnirs_variable_length_roi_v2_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    features = []
    file_audit = []
    channel_names = {}
    if source_decisions:
        write(out / "source_decisions_private.csv", source_decisions)
    for idx, (path, meta) in enumerate(files, 1):
        p = Path(path)
        sid = meta["current_subject_id"]
        sums = defaultdict(lambda: [0.0, 0])
        rows = 0
        bad = 0
        first_time = None
        last_time = None
        try:
            with p.open("r", encoding="utf-8", errors="ignore") as f:
                lines = []
                for _ in range(35):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line.rstrip("\r\n"))
                if len(lines) < 35:
                    raise ValueError("short_header")
                # Header line 33 identifies each triplet's channel; data line 34 identifies oxy/deoxy/total.
                channel_line = lines[33].split("\t")
                data_header = lines[34].split("\t")
                groups = parse_channel_groups(channel_line)
                channel_names[path] = [g[0] for g in groups]
                for line in f:
                    parts = line.rstrip("\r\n").split("\t")
                    if len(parts) < 4:
                        continue
                    t = num(parts[0])
                    if t is None:
                        continue
                    if first_time is None:
                        first_time = t
                    last_time = t
                    if t < 0 or t >= 1200:
                        continue
                    block = int(t // 300)
                    rows += 1
                    # triplets start at column 4 (index 4), one channel per three columns.
                    for k, (ch, j) in enumerate(groups):
                        roi = ch_roi.get(ch)
                        if roi is None:
                            continue
                        base = j
                        if base + 1 >= len(parts):
                            bad += 1
                            continue
                        for metric, off in [("HbO", 0), ("HbR", 1)]:
                            v = num(parts[base + off])
                            if v is not None:
                                sums[(block, roi, metric)][0] += v
                                sums[(block, roi, metric)][1] += 1
            # Use actual observed VAS only; no bridging and no marker imputation.
            for block in range(4):
                vals = []
                for minute in range(block * 5 + 1, min(20, block * 5 + 5) + 1):
                    v = num(vas[sid].get(f"VAS_{minute}min", ""))
                    if v is not None:
                        vals.append(v)
                if len(vals) < 3:
                    continue
                for roi in sorted(set(ch_roi.values())):
                    row = {
                        "subject_id": sid,
                        "path": path,
                        "block": block,
                        "vas_minutes": f"{block * 5 + 1}-{min(20, block * 5 + 5)}",
                        "roi_label": roi,
                        "vas_n": len(vals),
                        "vas_mean": float(np.mean(vals)),
                    }
                    ok = False
                    for metric in ("HbO", "HbR"):
                        total, n = sums[(block, roi, metric)]
                        row[metric] = float(total / n) if n else ""
                        ok = ok or n > 0
                    if ok:
                        features.append(row)
            file_audit.append(
                {
                    "subject_id": sid,
                    "path": path,
                    "status": "processed",
                    "rows_0_20min": rows,
                    "nonfinite_or_short_rows": bad,
                    "first_time_s": first_time,
                    "last_time_s": last_time,
                    "channels_detected": len(groups),
                    "roi_channels_mapped": sum(ch in ch_roi for ch, _ in groups),
                }
            )
        except Exception as e:
            file_audit.append(
                {"subject_id": sid, "path": path, "status": "failed", "error": str(e)}
            )
        if idx % 20 == 0:
            print(f"fNIRS {idx}/{len(files)} features={len(features)}", flush=True)
    grouped = defaultdict(list)
    for r in features:
        grouped[(r["subject_id"], r["block"], r["vas_minutes"], r["roi_label"])].append(
            r
        )
    agg = []
    for key, rs in grouped.items():
        base = rs[0].copy()
        for metric in ("HbO", "HbR"):
            vals = [float(r[metric]) for r in rs if r.get(metric, "") != ""]
            base[metric] = float(np.mean(vals)) if vals else ""
        agg.append(base)
    write(out / "file_audit_private.csv", file_audit)
    write(out / "roi_block_features_private.csv", agg)
    write(
        out / "excluded_ambiguous_subjects_private.csv",
        [
            {"subject_id": s, "reason": "multiple_different_hash_E_fNIRS_records"}
            for s in unresolved_subjects
        ],
    )
    summary = {
        "candidate_mapping_files": len(mapping),
        "canonical_files": len(files),
        "excluded_ambiguous_subjects": len(unresolved_subjects),
        "processed_files": sum(r["status"] == "processed" for r in file_audit),
        "failed_files": sum(r["status"] == "failed" for r in file_audit),
        "feature_rows": len(agg),
        "subjects": len({r["subject_id"] for r in agg}),
        "status": "completed_algorithmic_roi_extraction_pending_model",
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest = {
        "status": "completed",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "revision": subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip(),
        "config_sha256": sha(CFG),
        "vas_sha256": sha(VAS),
        "roi_mapping_sha256": sha(ROI),
        "code_sha256": sha(Path(__file__)),
        "summary": summary,
    }
    manifest["relocation_sha256"] = {
        str(p): sha(p)
        for p in relocation_evidence() + [ROOT / "scripts/path_resolver.py", MAP]
    }
    manifest["source_adjudication_sha256"] = {str(p): sha(p) for p in decision_evidence}
    (out / "frozen_config.json").write_bytes(CFG.read_bytes())
    (out / "execution_script.py").write_bytes(Path(__file__).read_bytes())
    manifest["config_path"] = str(CFG)
    manifest["signals_sha256"] = {
        r["_resolved"]: r["_hash"] for rs in by_subject.values() for r in rs
    }
    manifest["outputs_sha256"] = {
        p.name: sha(p)
        for p in out.iterdir()
        if p.is_file() and p.name != "run_manifest.json"
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out / "REPORT.md").write_text(
        "# fNIRS 变长 VAS 区域提取\n\n本轮按用户确认采用分钟级协议相对匹配，并使用确认的 42 通道—ROI 映射。输出为算法提取的 5 分钟 HbO/HbR 区域特征；未声明绝对浓度单位，不跨缺口、不补 VAS。人工复核清单保留在 file_audit_private.csv。\n\n```json\n"
        + json.dumps(summary, indent=2, ensure_ascii=False)
        + "\n```\n",
        encoding="utf-8",
    )
    print(out)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
