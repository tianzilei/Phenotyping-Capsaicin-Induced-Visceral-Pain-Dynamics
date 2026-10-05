"""Algorithmic ECG candidate quality stratification without a reference label."""

from __future__ import annotations
import csv
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "08_outputs/ecg_candidate_quality_20260929T130000Z"
sys.path.insert(0, str(ROOT / "scripts"))
from run_rest_post_hrv_pair import pairs, read

TOL = 0.03
RRLO = 0.3
RRHI = 1.8
JUMP = 0.25


def sha(p):
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def ecg_indices(names):
    x = [i for i, n in enumerate(names) if "ECG" in n.upper()]
    return x[:3] if len(x) >= 3 else ([2, 3, 4] if len(names) == 5 else [3, 4, 5])


def lead_peaks(x, fs):
    sos = signal.butter(4, [8, 28], btype="bandpass", fs=fs, output="sos")
    y = signal.sosfiltfilt(sos, x)
    n = max(1, round(0.12 * fs))
    e = np.convolve(np.gradient(y) ** 2, np.ones(n) / n, mode="same")
    mad = np.median(abs(e - np.median(e))) * 1.4826
    p, _ = signal.find_peaks(
        e, distance=round(0.2 * fs), prominence=max(2 * mad, np.finfo(float).eps)
    )
    return p.astype(int), y


def consensus(ps, fs):
    allp = sorted(set(int(v) for p in ps for v in p))
    used = []
    events = []
    tol = round(TOL * fs)
    for p in allp:
        near = [int(a[np.argmin(abs(a - p))]) for a in ps if np.any(abs(a - p) <= tol)]
        if len(near) >= 2:
            z = int(round(np.median(near)))
            if not events or z - events[-1] >= round(0.2 * fs):
                events.append(z)
    return np.asarray(events, dtype=int)


def morph_score(raw, events, fs):
    sos = signal.butter(4, [8, 28], btype="bandpass", fs=fs, output="sos")
    ys = np.asarray([signal.sosfiltfilt(sos, x) for x in raw])
    pieces = []
    aoff = round(-0.05 * fs)
    boff = round(0.05 * fs)
    for p in events:
        a, b = p + aoff, p + boff
        if a >= 0 and b <= ys.shape[1]:
            pieces.append(ys[:, a:b])
    if len(pieces) < 3:
        return 0.0
    z = np.asarray(pieces)
    templ = np.median(z, axis=0)
    vals = []
    for q in z:
        for ch in range(z.shape[1]):
            if np.std(q[ch]) > 0 and np.std(templ[ch]) > 0:
                vals.append(max(0, float(np.corrcoef(q[ch], templ[ch])[0, 1])))
    return float(np.median(vals)) if vals else 0.0


def rr_score(events, fs):
    rr = np.diff(events) / fs
    if len(rr) == 0:
        return 0.0
    ok = (rr >= RRLO) & (rr <= RRHI)
    pair = (
        ok[1:]
        & ok[:-1]
        & ((np.abs(rr[1:] - rr[:-1]) / np.maximum(rr[:-1], 1e-12)) <= JUMP)
        if len(rr) > 1
        else np.array([], bool)
    )
    return float(np.mean(ok)) * 0.5 + (float(np.mean(pair)) if len(pair) else 0.0) * 0.5


def neg_score(raw, fs, events):
    rng = np.random.default_rng(20260929)
    shuffled = np.asarray([x[rng.permutation(len(x))] for x in raw])
    ps = [lead_peaks(x, fs)[0] for x in shuffled]
    n = len(consensus(ps, fs))
    d = max(len(events), 1)
    return float(max(0, 1 - n / d))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    hashes = {}
    for sid, stem, bp, ep, base in pairs():
        for stage, path in ((base, bp), ("E", ep)):
            row = {
                "subject_id": sid,
                "recording_stem": stem,
                "stage": stage,
                "source_path": str(path),
            }
            try:
                arr, fs, names = read(path)
                idx = ecg_indices(names)
                raw = arr[idx]
                ps = []
                counts = []
                for x in raw:
                    p, _ = lead_peaks(x, fs)
                    ps.append(p)
                    counts.append(len(p))
                ev = consensus(ps, fs)
                allp = sorted(set(int(v) for a in ps for v in a))
                coincident = sum(
                    1
                    for p in allp
                    if sum(np.any(abs(a - p) <= round(TOL * fs)) for a in ps) >= 2
                )
                sm = float(coincident / max(len(allp), 1))
                s_m = morph_score(raw, ev, fs)
                s_rr = rr_score(ev, fs)
                s_neg = neg_score(raw, fs, ev)
                cqs = 0.35 * sm + 0.25 * s_m + 0.25 * s_rr + 0.15 * s_neg
                hard = len(ev) < 20 or s_neg < 0.5
                status = (
                    "RPEAK_QUALITY_FAILED"
                    if cqs < 0.7 or s_neg < 0.6
                    else (
                        "RPEAK_AUTO_ACCEPTED"
                        if cqs >= 0.85 and sm >= 0.8 and s_rr >= 0.85 and not hard
                        else "RPEAK_MANUAL_AUDIT_REQUIRED"
                    )
                )
                row.update(
                    {
                        "record_seconds": arr.shape[1] / fs,
                        "r_peaks": len(ev),
                        "lead_peak_counts": ";".join(map(str, counts)),
                        "s_multi": sm,
                        "s_morph": s_m,
                        "s_rr": s_rr,
                        "s_negative_control": s_neg,
                        "cqs": cqs,
                        "status": status,
                        "human_reference_required": bool(
                            status == "RPEAK_MANUAL_AUDIT_REQUIRED" or hard
                        ),
                        "semantic_note": "candidate_quality_not_accuracy",
                    }
                )
                hashes[str(path)] = sha(path)
            except Exception as ex:
                row.update(
                    {
                        "status": "RPEAK_QUALITY_FAILED",
                        "human_reference_required": True,
                        "error": f"{type(ex).__name__}: {ex}",
                    }
                )
            rows.append(row)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT / "ecg_candidate_quality.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    summary = {
        "records": len(rows),
        "auto_accepted": sum(r.get("status") == "RPEAK_AUTO_ACCEPTED" for r in rows),
        "manual_audit_required": sum(
            r.get("status") == "RPEAK_MANUAL_AUDIT_REQUIRED" for r in rows
        ),
        "quality_failed": sum(r.get("status") == "RPEAK_QUALITY_FAILED" for r in rows),
        "semantic_status": "candidate_quality_not_accuracy",
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": "config/ecg_candidate_quality_v1.json",
        "input_sha256": hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "summary": summary,
    }
    (OUT / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
