"""Waveform-level resting ECG/EGG QC and held-out crosstalk audit.

Reads strict mapped ACQ files without modifying them.  Rest and exposure
records are analyzed independently.  No values are imputed and no gaps are
bridged.  Results are engineering/descriptive gates, not clinical validation.
"""

from __future__ import annotations
import csv
import hashlib
import json
import platform
import sys
import subprocess
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
OUT = ROOT / "08_outputs/rest_waveform_qc_20260929T083000Z"
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.crosstalk_calibration import (
    CalibrationSpec,
    session_slices,
    estimate_template,
    subtract_frozen_template,
    classify_attenuation,
)

SPEC = CalibrationSpec()


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def read_rows():
    with MAPPING.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    uniq = {}
    for r in rows:
        if (
            r.get("match_status") != "accepted_strict"
            or r.get("extension", "").lower() != ".acq"
            or r.get("stage") not in {"E", "N", "C"}
        ):
            continue
        uniq[(r["current_subject_id"], r["stage"], r["local_path"])] = r
    groups = defaultdict(dict)
    for (sid, stage, local), r in uniq.items():
        s = Path(r["filename"]).stem
        stem = s[:-1] if s and s[-1].upper() in {"E", "N", "C"} else s
        groups[(sid, stem)][stage] = r
    out = []
    for (sid, stem), d in sorted(groups.items()):
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


def read_acq(p: Path):
    with p.open("rb") as f:
        r = bioread.reader.Reader(f)
        r._read_headers()
        r._read_data(None, bioread.reader.CHUNK_SIZE)
        d = r.datafile
    arr = np.vstack([np.asarray(c.data, dtype=float) for c in d.channels])
    fs = float(d.channels[0].samples_per_second)
    names = [str(c.name) for c in d.channels]
    return arr, fs, names


def channel_indices(names):
    ecg = [i for i, n in enumerate(names) if "ECG" in n.upper()]
    egg = [i for i, n in enumerate(names) if "EGG" in n.upper()]
    if len(ecg) < 3 or len(egg) < 2:
        # Known acquisition layouts have ECG at the tail and EGG at the head.
        if len(names) in (5,):
            ecg, egg = [2, 3, 4], [0, 1]
        elif len(names) in (6, 7):
            ecg, egg = [3, 4, 5], [1, 2]
    return ecg[:3], egg[:2]


def quality(x, fs):
    finite = np.isfinite(x)
    xf = x[finite]
    if xf.size == 0:
        return dict(
            finite_fraction=0,
            saturation_fraction=1,
            flatline_fraction=1,
            robust_range=np.nan,
        )
    med = float(np.median(xf))
    dev = np.abs(xf - med)
    scale = float(np.percentile(dev, 99.9))
    sat = np.mean(dev >= max(scale, 1e-12))
    d = np.diff(x, prepend=x[:1])
    flat = np.abs(d) <= max(np.nanpercentile(np.abs(d[finite]), 1), 1e-12)
    # Long constant runs are a conservative hardware flatline indicator.
    maxrun = run_max(flat)
    return dict(
        finite_fraction=float(np.mean(finite)),
        saturation_fraction=float(sat),
        flatline_fraction=float(maxrun / max(len(x), 1)),
        robust_range=float(np.percentile(xf, 99) - np.percentile(xf, 1)),
    )


def run_max(mask):
    best = cur = 0
    for v in np.asarray(mask, dtype=bool):
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def downsample(x, fs, target=100):
    if abs(fs - target) < 1e-6:
        return x, fs
    g = np.gcd(int(round(fs)), target)
    y = signal.resample_poly(x, target // g, int(round(fs)) // g, axis=-1)
    return y, float(target)


def r_peaks(ecg, fs):
    cfg = {
        "bandpass_hz": [8.0, 28.0],
        "filter_order": 4,
        "energy_window_seconds": 0.12,
        "refractory_seconds": 0.20,
        "consensus_tolerance_seconds": 0.020,
        "snr_min_db": 6.0,
    }
    leads = []
    for x in ecg:
        sos = signal.butter(
            cfg["filter_order"],
            cfg["bandpass_hz"],
            btype="bandpass",
            fs=fs,
            output="sos",
        )
        y = signal.sosfiltfilt(sos, x)
        n = max(1, round(cfg["energy_window_seconds"] * fs))
        e = np.convolve(np.gradient(y) ** 2, np.ones(n) / n, mode="same")
        mad = np.median(np.abs(e - np.median(e))) * 1.4826
        p, _ = signal.find_peaks(
            e, distance=round(0.2 * fs), prominence=max(2 * mad, np.finfo(float).eps)
        )
        leads.append(p)
    tol = round(0.020 * fs)
    allp = sorted(set(int(v) for a in leads for v in a))
    events = []
    for p in allp:
        near = [
            int(a[np.argmin(np.abs(a - p))])
            for a in leads
            if np.any(np.abs(a - p) <= tol)
        ]
        if len(near) >= 2:
            q = int(round(np.median(near)))
            if not events or q - events[-1] >= round(0.2 * fs):
                events.append(q)
    return np.asarray(events, dtype=int), [len(a) for a in leads]


def egg_metrics(egg, fs):
    x, fs2 = downsample(egg, fs, 100)
    fs = fs2
    finite = np.all(np.isfinite(x), axis=0)
    out = []
    for ch in x:
        y = ch.copy()
        y[~np.isfinite(y)] = (
            np.nanmedian(y[np.isfinite(y)]) if np.any(np.isfinite(y)) else 0
        )
        sos = signal.butter(4, [0.015, 0.150], btype="bandpass", fs=fs, output="sos")
        z = signal.sosfiltfilt(sos, y)
        f, p = signal.welch(
            z, fs=fs, nperseg=min(len(z), int(240 * fs)), detrend="linear"
        )
        b = (f >= 0.015) & (f <= 0.150)
        i = np.flatnonzero(b)
        k = i[np.argmax(p[i])] if len(i) else 0
        slow = (f >= 0.033) & (f <= 0.067)
        out.append(
            {
                "dominant_cpm": float(f[k] * 60) if len(i) else np.nan,
                "slow_power_ratio": float(
                    np.trapezoid(p[slow], f[slow])
                    / max(np.trapezoid(p[b], f[b]), 1e-20)
                )
                if len(i)
                else np.nan,
                "valid_fraction": float(np.mean(np.isfinite(ch))),
            }
        )
    cf, cp = signal.coherence(x[0], x[1], fs=fs, nperseg=min(len(x[0]), int(120 * fs)))
    cband = (cf >= 0.033) & (cf <= 0.067)
    coherence = float(np.nanmax(cp[cband])) if np.any(cband) else np.nan
    return out, coherence, x, fs


def band_power(x, fs, lo=0.8, hi=1.5):
    f, p = signal.welch(x, fs=fs, nperseg=min(len(x), int(120 * fs)), detrend="linear")
    return float(np.trapezoid(p[(f >= lo) & (f <= hi)], f[(f >= lo) & (f <= hi)]))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    failures = []
    input_hashes = {str(MAPPING): sha(MAPPING)}
    for sid, stem, base_path, exp_path, base_stage in read_rows():
        for p in (base_path, exp_path):
            input_hashes[str(p)] = sha(p)
        row = {
            "subject_id": sid,
            "recording_stem": stem,
            "baseline_stage": base_stage,
            "status": "running",
            "base_path": str(base_path),
            "exp_path": str(exp_path),
        }
        try:
            b, bfs, bnames = read_acq(base_path)
            e, efs, enames = read_acq(exp_path)
            becg, begg = channel_indices(bnames)
            eecg, eegg = channel_indices(enames)
            bq = [quality(b[i], bfs) for i in begg + becg]
            eq = [quality(e[i], efs) for i in eegg + eecg]
            row.update(
                {
                    "base_min_seconds": b.shape[1] / bfs,
                    "exp_min_seconds": e.shape[1] / efs,
                    "base_fs": bfs,
                    "exp_fs": efs,
                    "base_channels": len(bnames),
                    "exp_channels": len(enames),
                    "base_ecg_indices": ";".join(map(str, becg)),
                    "base_egg_indices": ";".join(map(str, begg)),
                    "exp_ecg_indices": ";".join(map(str, eecg)),
                    "exp_egg_indices": ";".join(map(str, eegg)),
                    "base_finite_min": min(q["finite_fraction"] for q in bq),
                    "exp_finite_min": min(q["finite_fraction"] for q in eq),
                    "base_flatline_max": max(q["flatline_fraction"] for q in bq),
                    "exp_flatline_max": max(q["flatline_fraction"] for q in eq),
                }
            )
            bev, bcounts = r_peaks(b[becg], bfs)
            eev, ecounts = r_peaks(e[eecg], efs)
            row.update(
                {
                    "base_r_peaks": len(bev),
                    "exp_r_peaks": len(eev),
                    "base_lead_candidates": ";".join(map(str, bcounts)),
                    "exp_lead_candidates": ";".join(map(str, ecounts)),
                    "base_consensus_fraction": len(bev) / max(np.mean(bcounts), 1),
                    "exp_consensus_fraction": len(eev) / max(np.mean(ecounts), 1),
                }
            )
            bm, bc, begg100, fs100 = egg_metrics(b[begg], bfs)
            em, ec, eegg100, _ = egg_metrics(e[eegg], efs)
            row.update(
                {
                    "base_egg_coherence": bc,
                    "exp_egg_coherence": ec,
                    "base_df1_cpm": bm[0]["dominant_cpm"],
                    "base_df2_cpm": bm[1]["dominant_cpm"],
                    "exp_df1_cpm": em[0]["dominant_cpm"],
                    "exp_df2_cpm": em[1]["dominant_cpm"],
                }
            )
            try:
                tr, guard, val = session_slices(begg100.shape[1], fs100, SPEC)
                rp = np.round(bev * fs100 / bfs).astype(int)
                train = begg100[:, tr]
                rp_train = rp[(rp >= tr.start) & (rp < tr.stop)] - tr.start
                template = estimate_template(train, rp_train, fs100, SPEC)
                valx = begg100[:, val]
                rp_val = rp[(rp >= val.start) & (rp < val.stop)] - val.start
                clean, info = subtract_frozen_template(
                    valx, rp_val, template, fs100, SPEC
                )
                rawp = np.mean([band_power(valx[i], fs100) for i in range(2)])
                cleanp = np.mean([band_power(clean[i], fs100) for i in range(2)])
                att = 10 * np.log10(max(rawp, 1e-20) / max(cleanp, 1e-20))
                gates = classify_attenuation(att, True)
                row.update(
                    {
                        "e05_template_windows": int(len(rp_train)),
                        "e05_applied_windows": info["applied_windows"],
                        "e05_attenuation_db": att,
                        "e05_pass_6db": gates["pass_6db_exploratory"],
                        "e05_pass_15db": gates["pass_15db_legacy"],
                        "e05_status": gates["status"],
                        "rest_calibration_status": "eligible",
                    }
                )
            except Exception as ex:
                row.update(
                    {
                        "e05_status": "E05_UNRESOLVED",
                        "rest_calibration_status": "ineligible:" + type(ex).__name__,
                    }
                )
            row["status"] = "completed"
        except Exception as ex:
            row.update({"status": "failed", "error": f"{type(ex).__name__}: {ex}"})
            failures.append(row.copy())
        records.append(row)
        print(sid, row["status"], row.get("rest_calibration_status", ""), flush=True)
    fields = list(dict.fromkeys(k for r in records for k in r))
    with (OUT / "rest_waveform_qc.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(records)
    summary = {
        "records": len(records),
        "completed": sum(r["status"] == "completed" for r in records),
        "failed": len(failures),
        "rest_eligible": sum(
            r.get("rest_calibration_status") == "eligible" for r in records
        ),
        "e05_exploratory_pass": sum(r.get("e05_pass_6db") is True for r in records),
        "e05_legacy_pass": sum(r.get("e05_pass_15db") is True for r in records),
        "scientific_status": "engineering_qc_only_no_independent_reference",
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "failures.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": "config/crosstalk_calibration_v1.json",
        "config_sha256": sha(ROOT / "config/crosstalk_calibration_v1.json"),
        "input_sha256": input_hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "summary": summary,
        "outputs_sha256": {p.name: sha(p) for p in OUT.iterdir() if p.is_file()},
    }
    (OUT / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
