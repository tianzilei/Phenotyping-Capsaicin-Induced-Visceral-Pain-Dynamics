from __future__ import annotations
import csv
import json
import math
from pathlib import Path
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RUN = sorted(
    (ROOT / "08_outputs").glob("reanalysis_neurokit_fnirsflow_*"),
    key=lambda p: p.stat().st_mtime,
)[-1]
ECG = sorted(
    (ROOT / "08_outputs").glob("complete_physiology_*"), key=lambda p: p.stat().st_mtime
)[-1]
VAS = (
    ROOT
    / "08_outputs/reanalysis_20260926_20260925T165400Z_c9b9d41d/vas_models/vas_long.csv"
)


def read(p):
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(p, rows):
    rows = list(rows)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def num(x):
    try:
        return float(x)
    except:
        return float("nan")


def corr(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 3 or np.ptp(x[m]) == 0 or np.ptp(y[m]) == 0:
        return {"n": int(m.sum()), "r": None, "p": None}
    r, p = stats.pearsonr(x[m], y[m])
    return {"n": int(m.sum()), "r": float(r), "p": float(p)}


def main():
    vas = {
        (r["subject_id"], int(r["time_min"])): num(r["vas"])
        for r in read(VAS)
        if r.get("status") == "observed"
    }
    ecg = {}
    for r in read(ECG / "ecg_windows_private.csv"):
        if str(r.get("qc_pass", "")).lower() != "true":
            continue
        sid = r.get("subject_id", "")
        minute = int(r.get("minute_index", int(float(r.get("window_index", 0))) + 1))
        key = (sid, minute)
        ecg.setdefault(key, []).append(r)
    er = []
    for key, rs in ecg.items():
        er.append(
            {
                "subject_id": key[0],
                "minute": key[1],
                "vas": vas.get(key, ""),
                "mean_hr_bpm": float(
                    np.nanmean([num(x.get("mean_hr_bpm")) for x in rs])
                ),
                "HRV_RMSSD": float(np.nanmean([num(x.get("HRV_RMSSD")) for x in rs])),
                "n_channels": len(rs),
            }
        )
    write(RUN / "length_aligned_ecg_vas_private.csv", er)
    fr = []
    for r in read(RUN / "fnirs_channel_window_features_private.csv"):
        if r.get("qc_status") != "pass" or r.get("feature_name") != "mean":
            continue
        minute = int(r["window_id"].lstrip("m"))
        fr.append(
            {
                "subject_id": r["person_id"],
                "minute": minute,
                "roi_label": r.get("roi_label", ""),
                "chromophore": r.get("chromophore", ""),
                "vas": vas.get((r["person_id"], minute), ""),
                "value": r.get("feature_value", ""),
            }
        )
    write(RUN / "length_aligned_fnirs_vas_channel_means_private.csv", fr)
    joined = []
    for r in fr:
        if r["vas"] != "":
            joined.append(r)
    results = []
    for roi in sorted({r["roi_label"] for r in joined}):
        for chrom in ("hbo", "hbr"):
            rr = [
                r for r in joined if r["roi_label"] == roi and r["chromophore"] == chrom
            ]
            by = {}
            for r in rr:
                by.setdefault((r["subject_id"], r["minute"]), []).append(
                    num(r["value"])
                )
            vals = [
                (float(np.nanmean(v)), vas.get(k, float("nan"))) for k, v in by.items()
            ]
            c = corr([x[0] for x in vals], [x[1] for x in vals])
            c.update(
                {
                    "roi_label": roi,
                    "chromophore": chrom,
                    "estimand": "exploratory length-aligned pooled same-minute correlation",
                    "n_subjects": len({k[0] for k in by}),
                    "n_windows": len(vals),
                }
            )
            results.append(c)
    for metric in ("mean_hr_bpm", "HRV_RMSSD"):
        rr = [r for r in er if r["vas"] != ""]
        c = corr([r[metric] for r in rr], [num(r["vas"]) for r in rr])
        c.update(
            {
                "roi_label": "",
                "chromophore": metric,
                "estimand": "exploratory length-aligned pooled same-minute correlation",
                "n_subjects": len({r["subject_id"] for r in rr}),
                "n_windows": len(rr),
            }
        )
        results.append(c)
    write(RUN / "length_aligned_associations_private.csv", results)
    summary = {
        "ecg_joined_windows": len([r for r in er if r["vas"] != ""]),
        "ecg_joined_subjects": len({r["subject_id"] for r in er if r["vas"] != ""}),
        "fnirs_joined_channel_windows": len(joined),
        "fnirs_joined_subjects": len({r["subject_id"] for r in joined}),
        "association_rows": len(results),
        "status": "exploratory_length_aligned_not_independently_validated",
    }
    (RUN / "length_aligned_association_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
