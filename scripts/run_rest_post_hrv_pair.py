"""Algorithmic, within-subject resting/post ECG NN-HRV pairing."""

from __future__ import annotations
import csv
import hashlib
import json
import platform
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy import signal
import bioread

ROOT = Path(__file__).resolve().parents[1]
MAPPING = (
    ROOT
    / "01_data/bids_capsaicin_20260925/sourcedata/migration/subject_to_files_D_private.csv"
)
OUT = ROOT / "08_outputs/rest_post_hrv_pair_20260929T090000Z"


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def pairs():
    with MAPPING.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    u = {}
    for r in rows:
        if (
            r.get("match_status") == "accepted_strict"
            and r.get("extension", "").lower() == ".acq"
            and r.get("stage") in {"E", "N", "C"}
        ):
            u[(r["current_subject_id"], r["stage"], r["local_path"])] = r
    g = defaultdict(dict)
    for (sid, st, loc), r in u.items():
        s = Path(r["filename"]).stem
        stem = s[:-1] if s and s[-1].upper() in "ENC" else s
        g[(sid, stem)][st] = r
    out = []
    for (sid, stem), d in sorted(g.items()):
        base = "N" if "N" in d else ("C" if "C" in d else "")
        if base and "E" in d:
            out.append(
                (
                    sid,
                    stem,
                    Path(d[base]["local_path"]),
                    Path(d["E"]["local_path"]),
                    base,
                )
            )
    return out


def read(p):
    with p.open("rb") as f:
        r = bioread.reader.Reader(f)
        r._read_headers()
        r._read_data(None, bioread.reader.CHUNK_SIZE)
        d = r.datafile
    return (
        np.vstack([np.asarray(c.data, float) for c in d.channels]),
        float(d.channels[0].samples_per_second),
        [str(c.name) for c in d.channels],
    )


def inds(names):
    ecg = [i for i, n in enumerate(names) if "ECG" in n.upper()]
    if len(ecg) < 3:
        ecg = [2, 3, 4] if len(names) == 5 else [3, 4, 5]
    return ecg[:3]


def peaks(ecg, fs):
    allp = []
    for x in ecg:
        sos = signal.butter(4, [8, 28], btype="bandpass", fs=fs, output="sos")
        y = signal.sosfiltfilt(sos, x)
        n = round(0.12 * fs)
        e = np.convolve(np.gradient(y) ** 2, np.ones(n) / n, mode="same")
        mad = np.median(abs(e - np.median(e))) * 1.4826
        p, _ = signal.find_peaks(
            e, distance=round(0.2 * fs), prominence=max(2 * mad, np.finfo(float).eps)
        )
        allp.append(p)
    tol = round(0.02 * fs)
    ev = []
    for p in sorted(set(int(v) for a in allp for v in a)):
        q = [int(a[np.argmin(abs(a - p))]) for a in allp if np.any(abs(a - p) <= tol)]
        if len(q) >= 2:
            z = int(round(np.median(q)))
            if not ev or z - ev[-1] >= round(0.2 * fs):
                ev.append(z)
    return np.asarray(ev, float) / fs


def metrics(times, duration):
    if len(times) < 3:
        return {
            "r_peaks": len(times),
            "rr_total": max(len(times) - 1, 0),
            "nn_valid": 0,
            "nn_valid_fraction": 0.0,
            "mean_hr_bpm": np.nan,
            "rmssd_ms": np.nan,
            "longest_contiguous_s": 0.0,
            "sampen_status": "ECG_SAMPEN_INESTIMABLE",
        }
    rr = np.diff(times)
    good = (rr >= 0.3) & (rr <= 2.0)
    # Adjacent jump and local robust outlier flags; no correction or interpolation.
    for i in range(1, len(rr)):
        good[i] &= abs(rr[i] - rr[i - 1]) / max(rr[i - 1], 1e-9) <= 0.2
    for i in range(len(rr)):
        lo = max(0, i - 5)
        hi = min(len(rr), i + 6)
        med = np.median(rr[lo:hi])
        mad = np.median(abs(rr[lo:hi] - med)) * 1.4826
        if mad > 0:
            good[i] &= abs(rr[i] - med) <= 3 * mad
    valid = rr[good]
    frac = float(np.mean(good)) if len(good) else 0.0
    # RMSSD only for adjacent original intervals, both valid; invalid gaps are skipped.
    adj = good[:-1] & good[1:]
    rmssd = (
        float(np.sqrt(np.mean(np.diff(rr[:-1][adj], axis=0) ** 2)) * 1000)
        if np.any(adj)
        else np.nan
    )
    # More direct adjacent interval differences (same indexing, no bridging).
    if np.any(adj):
        rmssd = float(np.sqrt(np.mean((rr[1:][adj] - rr[:-1][adj]) ** 2)) * 1000)
    meanhr = float(60 / np.mean(valid)) if len(valid) else np.nan
    starts = np.where(good)[0]
    longest = 0
    if len(starts):
        run = 1
        for a, b in zip(starts[:-1], starts[1:]):
            run = run + 1 if b == a + 1 else 1
            longest = max(longest, run)
        longest = max(longest, run) * float(np.median(rr[good]))
    return {
        "r_peaks": len(times),
        "rr_total": len(rr),
        "nn_valid": int(np.sum(good)),
        "nn_valid_fraction": frac,
        "mean_hr_bpm": meanhr,
        "rmssd_ms": rmssd,
        "longest_contiguous_s": float(longest),
        "sampen_status": "estimable_candidate"
        if longest >= 120
        else "ECG_SAMPEN_INESTIMABLE",
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    hashes = {str(MAPPING): sha(MAPPING)}
    for sid, stem, bp, ep, bs in pairs():
        hashes[str(bp)] = sha(bp)
        hashes[str(ep)] = sha(ep)
        row = {
            "subject_id": sid,
            "recording_stem": stem,
            "baseline_stage": bs,
            "base_path": str(bp),
            "post_path": str(ep),
        }
        try:
            b, bfs, bn = read(bp)
            e, efs, en = read(ep)
            bt = peaks(b[inds(bn)], bfs)
            et = peaks(e[inds(en)], efs)
            bm = metrics(bt, b.shape[1] / bfs)
            em = metrics(et, e.shape[1] / efs)
            for prefix, m in [("base", bm), ("post", em)]:
                for k, v in m.items():
                    row[prefix + "_" + k] = v
            row["paired_status"] = (
                "E07_TIER_C_ESTIMATED"
                if bm["nn_valid_fraction"] >= 0.85 and em["nn_valid_fraction"] >= 0.85
                else "E07_INVALID_QUALITY"
            )
            row["delta_mean_hr_bpm"] = (
                em["mean_hr_bpm"] - bm["mean_hr_bpm"]
                if np.isfinite(em["mean_hr_bpm"]) and np.isfinite(bm["mean_hr_bpm"])
                else np.nan
            )
            row["delta_rmssd_ms"] = (
                em["rmssd_ms"] - bm["rmssd_ms"]
                if np.isfinite(em["rmssd_ms"]) and np.isfinite(bm["rmssd_ms"])
                else np.nan
            )
        except Exception as ex:
            row.update(
                {
                    "paired_status": "E07_FAILED_INPUT",
                    "error": f"{type(ex).__name__}: {ex}",
                }
            )
        rows.append(row)
        print(sid, row["paired_status"], flush=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT / "rest_post_hrv.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    summary = {
        "pairs": len(rows),
        "tier_c_estimated": sum(
            r.get("paired_status") == "E07_TIER_C_ESTIMATED" for r in rows
        ),
        "invalid_quality": sum(
            r.get("paired_status") == "E07_INVALID_QUALITY" for r in rows
        ),
        "failed_input": sum(r.get("paired_status") == "E07_FAILED_INPUT" for r in rows),
        "scientific_status": "within_subject_algorithmic_descriptive_no_independent_reference",
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "run_manifest.json").write_text(
        json.dumps(
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "config": "config/crosstalk_calibration_v1.json",
                "input_sha256": hashes,
                "python": sys.version,
                "platform": platform.platform(),
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
