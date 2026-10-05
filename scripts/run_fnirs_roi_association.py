"""Fit exploratory subject-fixed-effects associations for extracted fNIRS ROI features."""

import csv
import json
import hashlib
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = sorted(
    (ROOT / "08_outputs").glob("fnirs_variable_length_roi_*"), key=lambda p: p.name
)[-1]
CFG = ROOT / "config/fnirs_variable_length_roi_v2.json"


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


def beta(rows, key):
    y = np.array([float(r["vas_mean"]) for r in rows])
    x = np.array([float(r[key]) for r in rows])
    s = [r["subject_id"] for r in rows]
    b = [r["block"] for r in rows]
    cols = [np.ones(len(rows))]
    for v in sorted(set(s))[1:]:
        cols.append(np.array([z == v for z in s], float))
    for v in sorted(set(b))[1:]:
        cols.append(np.array([z == v for z in b], float))
    Z = np.column_stack(cols)
    ry = y - Z @ np.linalg.lstsq(Z, y, rcond=None)[0]
    rx = x - Z @ np.linalg.lstsq(Z, x, rcond=None)[0]
    return float(rx @ ry / (rx @ rx)) if rx @ rx > 1e-12 else None


def boot(rows, key, B=2000, seed=20260921):
    rng = np.random.default_rng(seed)
    ids = sorted({r["subject_id"] for r in rows})
    out = []
    for _ in range(B):
        take = rng.choice(ids, len(ids), replace=True)
        s = [r for i in take for r in rows if r["subject_id"] == i]
        v = beta(s, key)
        if v is not None:
            out.append(v)
    return {
        "n_bootstrap": len(out),
        "beta_low": float(np.quantile(out, 0.025)) if out else None,
        "beta_median": float(np.median(out)) if out else None,
        "beta_high": float(np.quantile(out, 0.975)) if out else None,
    }


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    bootstrap_replicates = int(cfg["inference"]["bootstrap_replicates"])
    src = read(SOURCE / "roi_block_features_private.csv")
    # Keep only finite HbO/HbR values, and require >=2 observed blocks for each subject-ROI family.
    groups = {}
    for r in src:
        for metric in ("HbO", "HbR"):
            try:
                float(r[metric])
                float(r["vas_mean"])
            except:
                continue
            groups.setdefault((r["roi_label"], metric), []).append(r)
    rows = []
    results = []
    for (roi, metric), rs in sorted(groups.items()):
        c = Counter(r["subject_id"] for r in rs)
        keep = {s for s, n in c.items() if n >= 2}
        rr = [r for r in rs if r["subject_id"] in keep]
        if len(keep) < 10:
            continue
        v = beta(rr, metric)
        results.append(
            {
                "roi_label": roi,
                "metric": metric,
                "n_subjects": len(keep),
                "n_rows": len(rr),
                "beta_vas_per_unit": v,
                **boot(rr, metric, B=bootstrap_replicates),
                "estimand": "exploratory within-subject association; minute-scale protocol-relative ROI feature",
            }
        )
        rows.extend(dict(r, model_eligible="True") for r in rr)
    out = (
        ROOT
        / "08_outputs"
        / (
            "fnirs_roi_association_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    write(out / "model_input_private.csv", rows)
    write(out / "roi_association_results.csv", results)
    summary = {
        "source_run": str(SOURCE),
        "input_rows": len(src),
        "model_input_rows": len(rows),
        "roi_metric_models": len(results),
        "rois": sorted({r["roi_label"] for r in results}),
        "bootstrap_replicates": bootstrap_replicates,
        "status": "completed_exploratory_roi_association",
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
        "source_sha256": sha(SOURCE / "roi_block_features_private.csv"),
        "code_sha256": sha(Path(__file__)),
        "summary": summary,
    }
    (out / "frozen_config.json").write_bytes(CFG.read_bytes())
    (out / "execution_script.py").write_bytes(Path(__file__).read_bytes())
    manifest["config_path"] = str(CFG)
    manifest["outputs_sha256"] = {
        p.name: sha(p)
        for p in out.iterdir()
        if p.is_file() and p.name != "run_manifest.json"
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report = [
        "# fNIRS ROI—VAS 关联（算法探索性结果）",
        "",
        "采用用户确认的分钟级协议相对匹配和 42 通道—ROI 映射。每个 ROI—指标模型使用受试者固定效应、5 分钟区块效应，并以受试者重抽样给出 bootstrap 区间。HbO/HbR 仍是厂商处理 Hb 导出值，未声明绝对浓度单位；结果不作因果或机制解释。",
        "",
        json.dumps(summary, ensure_ascii=False, indent=2),
    ]
    (out / "REPORT.md").write_text("\n\n".join(report) + "\n", encoding="utf-8")
    print(out)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
