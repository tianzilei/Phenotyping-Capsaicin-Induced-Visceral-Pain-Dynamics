"""Held-out ECG->EGG crosstalk audits for the frozen resting calibration.

This is an audit product only.  It never edits source ACQ files, fills gaps,
or treats an audit pass as physiological validation.
"""

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
OUT = ROOT / "08_outputs/rest_crosstalk_audit_20260929T100000Z"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from run_rest_waveform_qc import (
    read_rows,
    read_acq,
    channel_indices,
    downsample,
    r_peaks,
    SPEC,
)
from capsaicin.crosstalk_calibration import (
    session_slices,
    estimate_template,
    subtract_frozen_template,
)

FS = 100.0
INJECT_CPM = 3.0
INJECT_AMPLITUDE = 50.0  # audit assumption: raw ACQ EGG unit is microvolt-like


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def qrs_rms(x, fs, peaks):
    sos = signal.butter(4, [8.0, 25.0], btype="bandpass", fs=fs, output="sos")
    z = signal.sosfiltfilt(sos, x)
    vals = []
    for p in peaks:
        a, b = int(p - 0.100 * fs), int(p + 0.150 * fs)
        if a >= 0 and b <= len(z):
            vals.append(float(np.sqrt(np.mean(z[a:b] ** 2))))
    return np.asarray(vals)


def fit_sine(x, fs, cpm=INJECT_CPM):
    t = np.arange(len(x), dtype=float) / fs
    w = 2 * np.pi * cpm / 60.0
    A = np.column_stack([np.sin(w * t), np.cos(w * t)])
    beta, *_ = np.linalg.lstsq(A, x, rcond=None)
    fit = A @ beta
    amp = float(np.hypot(beta[0], beta[1]))
    phase = float(np.arctan2(beta[1], beta[0]))
    return amp, phase, fit


def injection_audit(raw, peaks, template, fs):
    t = np.arange(raw.shape[1], dtype=float) / fs
    w = 2 * np.pi * INJECT_CPM / 60.0
    injected = np.tile(INJECT_AMPLITUDE * np.sin(w * t), (raw.shape[0], 1))
    base, _ = subtract_frozen_template(raw, peaks, template, fs, SPEC)
    pert, _ = subtract_frozen_template(raw + injected, peaks, template, fs, SPEC)
    rows = []
    for ch in range(raw.shape[0]):
        recovered = pert[ch] - base[ch]
        amp, phase, fit = fit_sine(recovered, fs)
        target_phase = 0.0
        phase_err = float(
            np.arctan2(np.sin(phase - target_phase), np.cos(phase - target_phase))
        )
        rmse = float(
            np.sqrt(np.mean((recovered - injected[ch]) ** 2)) / INJECT_AMPLITUDE
        )
        rows.append((amp / INJECT_AMPLITUDE, abs(phase_err), rmse))
    return rows


def projection_audit(raw, peaks, template, fs):
    vals = []
    left, right = round(SPEC.window_seconds[0] * fs), round(SPEC.window_seconds[1] * fs)
    for p in np.asarray(peaks, dtype=int):
        a, b = p + left, p + right
        if a < 0 or b > raw.shape[1]:
            continue
        for ch in range(raw.shape[0]):
            y = raw[ch, a:b]
            t = template[ch]
            yc, tc = y - y.mean(), t - t.mean()
            den = float(np.dot(tc, tc))
            if den <= 1e-15 or np.std(yc) <= 0:
                continue
            vals.append(
                (
                    float(np.corrcoef(yc, tc)[0, 1]),
                    float(np.dot(yc, tc) / den),
                    float(np.sqrt(np.mean(yc**2))),
                    float(np.sqrt(np.mean(tc**2))),
                )
            )
    return np.asarray(vals, dtype=float)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, hashes = [], {}
    mapping = (
        ROOT
        / "01_data/bids_capsaicin_20260925/sourcedata/migration/subject_to_files_D_private.csv"
    )
    hashes[str(mapping)] = sha(mapping)
    for sid, stem, base_path, exp_path, base_stage in read_rows():
        row = {"subject_id": sid, "recording_stem": stem, "status": "E05_UNRESOLVED"}
        try:
            hashes[str(base_path)] = sha(base_path)
            b, bfs, bn = read_acq(base_path)
            _, begg = channel_indices(bn)
            egg, fs = downsample(b[begg], bfs, int(FS))
            ecg_idx, _ = channel_indices(bn)
            ev, _ = r_peaks(b[ecg_idx], bfs)
            ev = np.round(ev * fs / bfs).astype(int)
            tr, guard, val = session_slices(egg.shape[1], fs, SPEC)
            rp_train = ev[(ev >= tr.start) & (ev < tr.stop)] - tr.start
            rp_val = ev[(ev >= val.start) & (ev < val.stop)] - val.start
            template = estimate_template(egg[:, tr], rp_train, fs, SPEC)
            raw = egg[:, val]
            clean, info = subtract_frozen_template(raw, rp_val, template, fs, SPEC)
            before = qrs_rms(raw.mean(axis=0), fs, rp_val)
            after = qrs_rms(clean.mean(axis=0), fs, rp_val)
            n = min(len(before), len(after))
            before, after = before[:n], after[:n]
            event_db = 10 * np.log10(
                np.maximum(before, 1e-12) ** 2 / np.maximum(after, 1e-12) ** 2
            )
            inj = injection_audit(raw, rp_val, template, fs)
            proj = projection_audit(raw, rp_val, template, fs)
            null = np.zeros_like(raw)
            null_out, _ = subtract_frozen_template(null, rp_val, template, fs, SPEC)
            f, p = signal.welch(
                null_out.mean(axis=0),
                fs=fs,
                nperseg=min(len(null_out[0]), int(120 * fs)),
                detrend="linear",
            )
            band = (f >= 0.033) & (f <= 0.067)
            null_rms = (
                float(np.sqrt(np.trapezoid(p[band], f[band]))) if np.any(band) else 0.0
            )
            ref_rms = INJECT_AMPLITUDE / np.sqrt(2)
            null_db = float(20 * np.log10(max(null_rms, 1e-15) / ref_rms))
            inj_amp = float(np.median([x[0] for x in inj]))
            inj_phase = float(np.max([x[1] for x in inj]))
            inj_rmse = float(np.max([x[2] for x in inj]))
            event_med = float(np.median(event_db)) if len(event_db) else np.nan
            row.update(
                {
                    "status": "E05_EXPLORATORY_PASSED"
                    if event_med >= 6
                    and inj_rmse <= 0.03
                    and inj_phase <= 0.05
                    and null_db <= -60
                    else "E05_UNRESOLVED",
                    "validation_events": int(len(rp_val)),
                    "applied_windows": int(info["applied_windows"]),
                    "event_qrs_attenuation_db_median": event_med,
                    "event_qrs_attenuation_db_p10": float(np.percentile(event_db, 10))
                    if len(event_db)
                    else np.nan,
                    "event_qrs_attenuation_db_p90": float(np.percentile(event_db, 90))
                    if len(event_db)
                    else np.nan,
                    "projection_corr_median": float(np.median(proj[:, 0]))
                    if len(proj)
                    else np.nan,
                    "projection_alpha_median": float(np.median(proj[:, 1]))
                    if len(proj)
                    else np.nan,
                    "projection_raw_rms_median": float(np.median(proj[:, 2]))
                    if len(proj)
                    else np.nan,
                    "projection_template_rms_median": float(np.median(proj[:, 3]))
                    if len(proj)
                    else np.nan,
                    "injection_amplitude_ratio_median": inj_amp,
                    "injection_phase_error_rad_max": inj_phase,
                    "injection_rmse_fraction_max": inj_rmse,
                    "null_slow_leakage_db": null_db,
                    "injection_amplitude_assumption": INJECT_AMPLITUDE,
                    "injection_frequency_cpm": INJECT_CPM,
                }
            )
        except Exception as ex:
            row.update(
                {"status": "E05_UNRESOLVED", "error": f"{type(ex).__name__}: {ex}"}
            )
        rows.append(row)
        print(sid, row["status"], flush=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT / "rest_crosstalk_audit.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    summary = {
        "records": len(rows),
        "exploratory_pass": sum(
            r.get("status") == "E05_EXPLORATORY_PASSED" for r in rows
        ),
        "unresolved": sum(r.get("status") == "E05_UNRESOLVED" for r in rows),
        "scientific_status": "engineering_audit_only",
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": "config/crosstalk_calibration_v1.json",
        "config_sha256": sha(ROOT / "config/crosstalk_calibration_v1.json"),
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
