"""Use the independently recorded PsychoPy evaluation clock as a per-record anchor."""

import csv
import json
import hashlib
import math
import platform
import subprocess
import uuid
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from path_resolver import resolve_external_path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


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


def parse_expstart(s):
    # 2024-11-02 16h47.33.497911 +0800
    return datetime.strptime(s.strip(), "%Y-%m-%d %Hh%M.%S.%f %z")


def parse_marker(s):
    # bioread string has e.g. 2024-11-02T09:04:51.633000+00:00
    m2 = re.search(r"date_created_utc: (\d{4}-\d\d-\d\dT[^ ]+)", s)
    return datetime.fromisoformat(m2.group(1)) if m2 else None


def reg(y, x, subjects=None, windows=None):
    """Subject- and window-adjusted association; no pooled repeated-window estimate."""
    y = np.asarray(y, float)
    x = np.asarray(x, float)
    if len(y) == 0:
        return None, None
    if subjects is None:
        subjects = ["all"] * len(y)
    if windows is None:
        windows = ["all"] * len(y)
    levels = [["intercept"], sorted(set(subjects))[1:], sorted(set(windows))[1:]]
    cols = [np.ones(len(y))]
    for vals in levels[1:]:
        for v in vals:
            cols.append(
                np.array(
                    [
                        1.0 if z == v else 0.0
                        for z in (subjects if vals is levels[1] else windows)
                    ]
                )
            )
    Z = np.column_stack(cols)
    try:
        rx = y - Z @ np.linalg.lstsq(Z, y, rcond=None)[0]
        qx = x - Z @ np.linalg.lstsq(Z, x, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None, None
    den = float(qx @ qx)
    return (
        float(qx @ rx / den) if den > 1e-12 else None,
        float(np.corrcoef(rx, qx)[0, 1])
        if den > 1e-12 and np.std(rx) > 0 and np.std(qx) > 0
        else None,
    )


def bootstrap(rows, xkey, seed=20260919, B=2000):
    rng = np.random.default_rng(seed)
    ids = sorted({r["subject_id"] for r in rows})
    vals = []
    for _ in range(B):
        take = rng.choice(ids, size=len(ids), replace=True)
        sample = []
        for i in take:
            sample.extend(r for r in rows if r["subject_id"] == i)
        b, c = reg(
            [r["vas_mean"] for r in sample],
            [r[xkey] for r in sample],
            [r["subject_id"] for r in sample],
            [r["window_index"] for r in sample],
        )
        if b is not None:
            vals.append(b)
    return dict(
        n_bootstrap=len(vals),
        beta_low=float(np.quantile(vals, 0.025)) if vals else None,
        beta_median=float(np.median(vals)) if vals else None,
        beta_high=float(np.quantile(vals, 0.975)) if vals else None,
    )


def main():
    source = ROOT / "08_outputs/complete_physiology_20260921T113635Z_cd5d9483"
    cfg = ROOT / "config/physiology_complete_v1.json"
    out = (
        ROOT
        / "08_outputs"
        / (
            "synced_physiology_association_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    vas = read(
        ROOT
        / "01_data/processed/e_coded_20260916T144438Z_5c144eb7/BaselineData_E_coded.csv"
    )
    vas = {r["ID"]: r for r in vas}
    logs = read(
        ROOT
        / "02_quality_control/reverse_enc_20260916T052506Z_def32d7d/psychopy_metadata_private.csv"
    )
    ecg = read(source / "ecg_windows_private.csv")
    recs = read(source / "recordings_private.csv")
    anchors = []
    log_by_code = {
        str(int(r["recording_code"])): r
        for r in logs
        if r.get("recording_code", "").isdigit()
    }
    # recording code is the numeric subject suffix in the accepted identity mapping.
    for rec in recs:
        sid = rec["subject_id"]
        code = sid.replace("SUBJECT", "").lstrip("0") or "0"
        log = log_by_code.get(code)
        if not log:
            continue
        try:
            d = list(
                csv.DictReader(
                    resolve_external_path(log["path"]).open(encoding="utf-8-sig")
                )
            )
            first = next(r for r in d if r.get("eval.started", "").strip())
            exp = parse_expstart(first["expStart"])
            eval_abs = exp + timedelta(seconds=float(first["eval.started"]))
            marker = parse_marker(rec.get("marker", ""))
            if (
                marker is None
            ):  # recordings_private does not include marker text; use source annotations
                marker_rows = read(source / "acq_annotations_private.csv")
                marker = next(
                    (
                        parse_marker(r["marker"])
                        for r in marker_rows
                        if r["path"] == rec["path"]
                    ),
                    None,
                )
            if marker is None:
                raise ValueError("missing ACQ file-header marker")
            delta = (marker - eval_abs.astimezone(timezone.utc)).total_seconds()
            anchors.append(
                dict(
                    subject_id=sid,
                    path=rec["path"],
                    log_path=log["path"],
                    eval_elapsed_s=float(first["eval.started"]),
                    acq_marker_utc=marker.isoformat(),
                    first_eval_utc=eval_abs.astimezone(timezone.utc).isoformat(),
                    acq_minus_eval_s=delta,
                    abs_delta_s=abs(delta),
                    anchor_status="pass" if abs(delta) <= 2 else "review",
                )
            )
        except Exception as e:
            anchors.append(
                dict(
                    subject_id=sid,
                    path=rec["path"],
                    log_path=log["path"],
                    anchor_status="fail",
                    error=str(e),
                )
            )
    # Only an independently dated, close start anchor may be used.
    accepted = {r["path"]: r for r in anchors if r["anchor_status"] == "pass"}
    features = []
    selected_keys = set()
    for r in ecg:
        if r.get("qc_pass") != "True" or r["path"] not in accepted:
            continue
        # one raw channel per subject/window, chosen before looking at VAS.
        key = (r["subject_id"], r["window_index"])
        if key in selected_keys:
            continue
        sid = r["subject_id"]
        w = int(r["window_index"])
        vals = (
            [float(vas[sid][f"VAS_{i}min"]) for i in range(w * 5 + 1, w * 5 + 6)]
            if sid in vas and w * 5 + 5 <= 20
            else []
        )
        if len(vals) != 5:
            continue
        features.append(
            dict(
                subject_id=sid,
                path=r["path"],
                window_index=w,
                vas_minutes=f"{w * 5 + 1}-{w * 5 + 5}",
                vas_mean=float(np.mean(vals)),
                mean_hr_bpm=float(r["mean_hr_bpm"]),
                HRV_RMSSD=float(r["HRV_RMSSD"]),
                channel=r["channel"],
                anchor_offset_s=accepted[r["path"]]["acq_minus_eval_s"],
            )
        )
        selected_keys.add(key)
    results = []
    for k, label in [("mean_hr_bpm", "Mean HR"), ("HRV_RMSSD", "RMSSD")]:
        beta, corr = reg(
            [r["vas_mean"] for r in features],
            [r[k] for r in features],
            [r["subject_id"] for r in features],
            [r["window_index"] for r in features],
        )
        bs = bootstrap(features, k)
        results.append(
            dict(
                exposure=k,
                n_subjects=len({r["subject_id"] for r in features}),
                n_windows=len(features),
                beta_vas_per_unit=beta,
                within_subject_corr=corr,
                **bs,
                estimand="within-subject concurrent association; exploratory; protocol-relative VAS blocks",
            )
        )
    for p, data in [
        ("anchor_audit_private.csv", anchors),
        ("association_input_private.csv", features),
        ("association_results.csv", results),
    ]:
        write(out / p, data)
    summary = dict(
        source_run=str(source),
        anchor_candidates=len(anchors),
        anchor_pass=sum(r["anchor_status"] == "pass" for r in anchors),
        anchor_review=sum(r["anchor_status"] == "review" for r in anchors),
        anchor_fail=sum(r["anchor_status"] == "fail" for r in anchors),
        association_subjects=len({r["subject_id"] for r in features}),
        association_windows=len(features),
        status="completed_exploratory_association" if features else "not_estimable",
    )
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest = dict(
        status="completed",
        created_utc=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(),
        revision=subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip(),
        code_sha256=sha(Path(__file__)),
        inputs_sha256={
            str(p): sha(p)
            for p in [
                cfg,
                source / "ecg_windows_private.csv",
                source / "recordings_private.csv",
                source / "acq_annotations_private.csv",
                ROOT
                / "01_data/processed/e_coded_20260916T144438Z_5c144eb7/BaselineData_E_coded.csv",
            ]
        },
        summary=summary,
    )
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    report = [
        "# 事件锚定后的完整 VAS—ECG 关联",
        "",
        "本轮使用每条 PsychoPy 日志的 `expStart + eval.started` 与对应 ACQ 文件头的 `date_created_utc` 建立记录级起始锚点。该锚点只把同一控制程序的第一个 VAS 评估时刻与 ACQ 记录起点进行逐例核对，不把协议起点称为吞服时刻。",
        "",
        json.dumps(summary, ensure_ascii=False, indent=2),
        "",
        "通过锚点（绝对差不超过2秒）的记录才进入关联；每个受试者每个5分钟窗预先取最小原始通道号的质控通过 ECG，不按VAS结果选通道。VAS结局是对应5个实际分钟评分的均值；没有跨缺口或补值。",
        "结果是受试者内同期关联的探索性描述，使用受试者重抽样区间，不作因果解释。HRV为NeuroKit2算法筛查后的记录相对指标，并非人工裁定临床NN。",
        "若需要发布剂量相对或机制性结论，仍需单独确认吞服事件；本轮只支持由日志评估时刻定义的协议相对VAS块。",
    ]
    (out / "REPORT.md").write_text("\n\n".join(report) + "\n", encoding="utf-8")
    manifest["outputs_sha256"] = {
        str(p.relative_to(out)): sha(p)
        for p in out.rglob("*")
        if p.is_file() and p.name != "run_manifest.json"
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
