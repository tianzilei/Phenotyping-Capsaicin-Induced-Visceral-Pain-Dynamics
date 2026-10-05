"""Exploratory protocol-relative association using variable-length observed VAS blocks."""

import csv
import json
import hashlib
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
    return datetime.strptime(s.strip(), "%Y-%m-%d %Hh%M.%S.%f %z")


def parse_marker(s):
    m = re.search(r"date_created_utc: (\d{4}-\d\d-\d\dT[^ ]+)", s)
    return datetime.fromisoformat(m.group(1)) if m else None


def reg(y, x, subjects, windows):
    y = np.asarray(y, float)
    x = np.asarray(x, float)
    cols = [np.ones(len(y))]
    for v in sorted(set(subjects))[1:]:
        cols.append(np.array([z == v for z in subjects], float))
    for v in sorted(set(windows))[1:]:
        cols.append(np.array([z == v for z in windows], float))
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
        b = reg(
            [r["vas_mean"] for r in s],
            [r[key] for r in s],
            [r["subject_id"] for r in s],
            [r["window_index"] for r in s],
        )
        if b is not None:
            vals.append(b)
    return {
        "n_bootstrap": len(vals),
        "beta_low": float(np.quantile(vals, 0.025)) if vals else None,
        "beta_median": float(np.median(vals)) if vals else None,
        "beta_high": float(np.quantile(vals, 0.975)) if vals else None,
    }


def main():
    source = sorted(
        (ROOT / "08_outputs").glob("variable_length_physiology_*"), key=lambda p: p.name
    )[-1]
    vas = {
        r["ID"]: r
        for r in read(
            ROOT
            / "01_data/processed/e_coded_20260916T144438Z_5c144eb7/BaselineData_E_coded.csv"
        )
    }
    logs = read(
        ROOT
        / "02_quality_control/reverse_enc_20260916T052506Z_def32d7d/psychopy_metadata_private.csv"
    )
    log_by_code = {
        str(int(r["recording_code"])): r
        for r in logs
        if r.get("recording_code", "").isdigit()
    }
    recs = read(source / "recordings_private.csv")
    anns = read(source / "acq_annotations_private.csv")
    anchors = []
    for rec in recs:
        sid = rec["subject_id"]
        code = sid.replace("SUBJECT", "").lstrip("0") or "0"
        log = log_by_code.get(code)
        try:
            d = list(
                csv.DictReader(
                    resolve_external_path(log["path"]).open(encoding="utf-8-sig")
                )
            )
            first = next(r for r in d if r.get("eval.started", "").strip())
            ev = parse_expstart(first["expStart"]) + timedelta(
                seconds=float(first["eval.started"])
            )
            marker = next(
                parse_marker(a["marker"]) for a in anns if a["path"] == rec["path"]
            )
            delta = (marker - ev.astimezone(timezone.utc)).total_seconds()
            anchors.append(
                {
                    "subject_id": sid,
                    "path": rec["path"],
                    "acq_minus_eval_s": delta,
                    "abs_delta_s": abs(delta),
                    "anchor_status": "pass" if abs(delta) <= 2 else "review",
                }
            )
        except Exception as e:
            anchors.append(
                {
                    "subject_id": sid,
                    "path": rec["path"],
                    "anchor_status": "fail",
                    "error": str(e),
                }
            )
    accepted = {r["path"]: r for r in anchors if r["anchor_status"] == "pass"}
    ecg = read(source / "ecg_windows_private.csv")
    features = []
    seen = set()
    for r in ecg:
        if r.get("qc_pass") != "True" or r["path"] not in accepted:
            continue
        sid = r["subject_id"]
        w = int(r["window_index"])
        nums = []
        for i in range(w * 5 + 1, min(20, w * 5 + 5) + 1):
            try:
                nums.append((i, float(vas[sid][f"VAS_{i}min"])))
            except (KeyError, ValueError, TypeError):
                nums.append((i, None))
        seg = []
        best = []
        for i, v in nums:
            if v is None:
                seg = []
            else:
                seg.append(v)
                best = max(best, seg, key=len) if seg else best
        if len(best) < 3:
            continue
        key = (sid, w)
        if key in seen:
            continue
        features.append(
            {
                "subject_id": sid,
                "path": r["path"],
                "window_index": w,
                "vas_minutes": f"{w * 5 + 1}-{w * 5 + 5}",
                "vas_n": len(best),
                "vas_mean": float(np.mean(best)),
                "mean_hr_bpm": float(r["mean_hr_bpm"]),
                "HRV_RMSSD": float(r["HRV_RMSSD"]),
                "channel": r["channel"],
                "anchor_offset_s": accepted[r["path"]]["acq_minus_eval_s"],
            }
        )
        seen.add(key)
    # Freeze the minimum of two usable windows per subject before inference.
    counts = {
        sid: sum(x["subject_id"] == sid for x in features)
        for sid in {x["subject_id"] for x in features}
    }
    excluded_subjects = sorted(sid for sid, n in counts.items() if n < 2)
    features = [x for x in features if x["subject_id"] not in excluded_subjects]
    out = (
        ROOT
        / "08_outputs"
        / (
            "variable_synced_physiology_association_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    results = []
    for key, label in [("mean_hr_bpm", "Mean HR"), ("HRV_RMSSD", "RMSSD")]:
        b = (
            reg(
                [r["vas_mean"] for r in features],
                [r[key] for r in features],
                [r["subject_id"] for r in features],
                [r["window_index"] for r in features],
            )
            if features
            else None
        )
        results.append(
            {
                "exposure": key,
                "n_subjects": len({r["subject_id"] for r in features}),
                "n_windows": len(features),
                "beta_vas_per_unit": b,
                **bootstrap(features, key),
                "estimand": "within-subject concurrent association; exploratory; protocol-relative observed VAS block",
            }
        )
    summary = {
        "source_run": str(source),
        "anchor_candidates": len(anchors),
        "anchor_pass": sum(r["anchor_status"] == "pass" for r in anchors),
        "anchor_review": sum(r["anchor_status"] == "review" for r in anchors),
        "anchor_fail": sum(r["anchor_status"] == "fail" for r in anchors),
        "pre_filter_association_subjects": len(counts),
        "excluded_below_minimum_windows": excluded_subjects,
        "association_subjects": len({r["subject_id"] for r in features}),
        "association_windows": len(features),
        "minimum_numeric_vas_per_block": 3,
        "minimum_windows_per_subject": 2,
        "status": "completed_exploratory_association" if features else "not_estimable",
    }
    write(out / "anchor_audit_private.csv", anchors)
    write(out / "association_input_private.csv", features)
    write(out / "association_results.csv", results)
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
        "code_sha256": sha(Path(__file__)),
        "inputs_sha256": {
            str(p): sha(p)
            for p in [
                source / "ecg_windows_private.csv",
                source / "recordings_private.csv",
                source / "acq_annotations_private.csv",
                ROOT
                / "01_data/processed/e_coded_20260916T144438Z_5c144eb7/BaselineData_E_coded.csv",
            ]
        },
        "summary": summary,
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out / "REPORT.md").write_text(
        "# 变长 VAS—NeuroKit2 生理关联\n\n本结果只使用独立起始锚点通过的记录，并在每个 5 分钟协议相对区块内使用至少 3 个真实连续数值 VAS；不跨 E/T 或缺口，不补值。结果是受试者内同期探索性关联，不代表精确给药时间、全程同步或因果关系。\n\n```json\n"
        + json.dumps(summary, indent=2, ensure_ascii=False)
        + "\n```\n",
        encoding="utf-8",
    )
    print(out)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
