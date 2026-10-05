"""Exploratory block-level EGG spectral-feature/fNIRS ROI association.

This intentionally does not estimate coherence or phase: the available EGG input is
independent-window spectral summaries, not a verified continuous synchronized series.
"""

import csv
import json
import hashlib
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/egg_fnirs_association_v1.json"
VAS = (
    ROOT
    / "01_data/processed/e_coded_20260916T144438Z_5c144eb7/BaselineData_E_coded.csv"
)
MAP = (
    ROOT
    / "02_quality_control/time_enc_20260916T123124Z_d4ff4af0/accepted_subject_to_files_private.csv"
)


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


def beta(rows, xkey, ykey):
    y = np.array([float(r[ykey]) for r in rows])
    x = np.array([float(r[xkey]) for r in rows])
    s = [r["subject_id"] for r in rows]
    b = [r["block"] for r in rows]

    # Fast alternating projection for subject and block fixed effects.
    def resid(v):
        z = v - v.mean()
        for _ in range(4):
            for g in (s, b):
                means = {
                    k: float(np.mean([z[i] for i, q in enumerate(g) if q == k]))
                    for k in set(g)
                }
                z = np.array([z[i] - means[q] for i, q in enumerate(g)])
            z -= z.mean()
        return z

    ry = resid(y)
    rx = resid(x)
    return float(rx @ ry / (rx @ rx)) if rx @ rx > 1e-12 else None


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    spectra = ROOT / cfg["egg_spectrum_run"]
    fnirs = ROOT / cfg["fnirs_roi_run"]
    mapping = {
        r["path"]: (r.get("current_subject_id"), r.get("stage")) for r in read(MAP)
    }
    sid_by_name = {Path(p).name: (sid, st) for p, (sid, st) in mapping.items()}
    vas = {r["ID"]: r for r in read(VAS)}
    egg = []
    for r in read(spectra / "windows_private.csv"):
        if (
            r.get("label") != "EGG100C"
            or r.get("spectral_status") != "computed_not_artifact_accepted"
            or r.get("stage") != "E"
        ):
            continue
        sid, st = mapping.get(
            r["path"], sid_by_name.get(Path(r["path"]).name, (None, None))
        )
        if not sid or sid not in vas:
            continue
        try:
            vals = {k: float(r[k]) for k in cfg["egg_features"]}
        except (ValueError, TypeError):
            continue
        egg.append(
            dict(
                subject_id=sid,
                block=int(r["window_index"]),
                path=r["path"],
                channel=r["channel"],
                **vals,
            )
        )
    # Average independent EGG channels per subject/block; retain channel count for review.
    eg = defaultdict(list)
    for r in egg:
        eg[(r["subject_id"], r["block"])].append(r)
    eggb = []
    for (sid, block), rs in eg.items():
        out = {"subject_id": sid, "block": block, "egg_channel_count": len(rs)}
        for k in cfg["egg_features"]:
            out[k] = float(np.mean([x[k] for x in rs]))
        eggb.append(out)
    frows = read(fnirs / "roi_block_features_private.csv")
    fgroups = defaultdict(list)
    for r in frows:
        try:
            float(r["vas_mean"])
            block = int(r["block"])
        except:
            continue
        # One fNIRS row per subject/block/ROI; deduplicate repeated recording paths by mean.
        fgroups[(r["subject_id"], block, r["roi_label"])].append(r)
    joined = []
    for (sid, block, roi), rs in fgroups.items():
        e = [x for x in eggb if x["subject_id"] == sid and x["block"] == block]
        if not e:
            continue
        vals = [
            float(vas[sid].get(f"VAS_{m}min", ""))
            for m in range(block * 5 + 1, min(20, block * 5 + 5) + 1)
            if vas[sid].get(f"VAS_{m}min", "") not in ("", "E", "T")
        ]
        if len(vals) < 3:
            continue
        e = e[0]
        r = rs[0]
        for metric in ("HbO", "HbR"):
            try:
                y = float(r[metric])
            except:
                continue
            joined.append(
                {
                    "subject_id": sid,
                    "block": block,
                    "roi_label": roi,
                    "vas_mean": float(np.mean(vals)),
                    "egg_channel_count": e["egg_channel_count"],
                    **{k: e[k] for k in cfg["egg_features"]},
                    "roi_value": y,
                    "fNIRS_metric": metric,
                }
            )
    results = []
    rng = np.random.default_rng(20260921)
    for roi in sorted({r["roi_label"] for r in joined}):
        for metric in ("HbO", "HbR"):
            rr = [
                r
                for r in joined
                if r["roi_label"] == roi and r["fNIRS_metric"] == metric
            ]
            for ek in cfg["egg_features"]:
                if len({r["subject_id"] for r in rr}) < 10:
                    continue
                b = beta(rr, ek, "vas_mean")
                br = beta(rr, ek, "roi_value")
                null = []
                by = defaultdict(list)
                for r in rr:
                    by[r["subject_id"]].append(r)
                for _ in range(int(cfg["bootstrap_replicates"])):
                    sr = []
                    for sid, rs in by.items():
                        vals = [x[ek] for x in rs]
                        perm = rng.permutation(vals)
                        sr += [dict(x, **{ek: float(v)}) for x, v in zip(rs, perm)]
                        z = beta(sr, ek, "roi_value")
                    if z is not None:
                        null.append(z)
                results.append(
                    {
                        "roi_label": roi,
                        "fNIRS_metric": metric,
                        "egg_feature": ek,
                        "n_subjects": len({r["subject_id"] for r in rr}),
                        "n_blocks": len(rr),
                        "beta_vas_per_egg_unit": b,
                        "beta_fNIRS_per_egg_unit": br,
                        "surrogate_median": float(np.median(null)) if null else None,
                        "surrogate_q025": float(np.quantile(null, 0.025))
                        if null
                        else None,
                        "surrogate_q975": float(np.quantile(null, 0.975))
                        if null
                        else None,
                        "estimand": cfg["estimand"],
                    }
                )
    out = (
        ROOT
        / "08_outputs"
        / (
            "egg_fnirs_association_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    write(out / "joined_features_private.csv", joined)
    write(out / "association_results.csv", results)
    summary = {
        "egg_channel_windows": len(egg),
        "egg_subject_blocks": len(eggb),
        "joined_rows": len(joined),
        "models": len(results),
        "status": "completed_exploratory_band_association_no_coherence",
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
        "mapping_sha256": sha(MAP),
        "egg_source_sha256": sha(spectra / "windows_private.csv"),
        "fnirs_source_sha256": sha(fnirs / "roi_block_features_private.csv"),
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
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (out / "REPORT.md").write_text(
        "# EGG–fNIRS 频带关联（探索性）\n\n本轮仅对独立 5 分钟窗口频带摘要和 fNIRS ROI 特征做协议相对、同期关联，并保存受试者内置换 surrogate。没有连续同步波形，因此不估计相干性、相位或机制效应；Hb 单位和给药绝对时间也未验证。\n\n```json\n"
        + json.dumps(summary, indent=2, ensure_ascii=False)
        + "\n```\n",
        encoding="utf-8",
    )
    print(out)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
