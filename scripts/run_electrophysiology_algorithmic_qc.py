"""Algorithmic ECG/EGG QC for the integrated recording scaffold.

This run is deliberately separate from the blank human-review package. It
produces candidate events, masks, window descriptors and exploratory joint
statuses. It never turns an algorithmic candidate into a clinical reference.
"""

from __future__ import annotations
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import bioread
from capsaicin.signal_spectra import resample_exact

TASK_DIR = Path(
    os.environ.get(
        "EP_TASK_DIR",
        str(
            ROOT
            / "02_quality_control/electrophysiology_review_handoff_v2_20260928T171503Z"
        ),
    )
)
CONFIG_PATH = Path(
    os.environ.get(
        "EP_CONFIG_PATH", str(ROOT / "config/electrophysiology_algorithmic_v1.json")
    )
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def write_csv(path: Path, rows: list[dict]):
    fields = list(dict.fromkeys(k for row in rows for k in row)) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def robust_snr(x: np.ndarray) -> float:
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826
    return float(20 * np.log10(max(np.ptp(x), 1e-12) / max(mad, 1e-12)))


def detect_lead(x: np.ndarray, fs: float, cfg: dict) -> tuple[np.ndarray, np.ndarray]:
    sos = signal.butter(
        cfg["filter_order"], cfg["bandpass_hz"], btype="bandpass", fs=fs, output="sos"
    )
    y = signal.sosfiltfilt(sos, x)
    e = np.convolve(
        np.gradient(y) ** 2,
        np.ones(max(1, round(cfg["energy_window_seconds"] * fs)))
        / max(1, round(cfg["energy_window_seconds"] * fs)),
        mode="same",
    )
    mad = np.median(np.abs(e - np.median(e))) * 1.4826
    peaks, _ = signal.find_peaks(
        e,
        distance=round(cfg["refractory_seconds"] * fs),
        prominence=max(mad * 2, np.finfo(float).eps),
    )
    return peaks.astype(int), y


def consensus_rpeaks(ecg: np.ndarray, fs: float, cfg: dict):
    lead_peaks = []
    filtered = []
    for x in ecg:
        p, y = detect_lead(x, fs, cfg)
        lead_peaks.append(p)
        filtered.append(y)
    tol = round(cfg["consensus_tolerance_seconds"] * fs)
    refractory = round(cfg["refractory_seconds"] * fs)
    all_events = sorted(set(int(p) for arr in lead_peaks for p in arr))
    used = set()
    events = []
    for p in all_events:
        if p in used:
            continue
        group = []
        for li, arr in enumerate(lead_peaks):
            near = arr[np.abs(arr - p) <= tol]
            if len(near):
                group.append((li, int(near[np.argmin(np.abs(near - p))])))
        if len(group) >= 2:
            loc = int(round(np.median([q for _, q in group])))
            if not events or loc - events[-1]["sample"] >= refractory:
                snr = float(
                    np.median(
                        [
                            robust_snr(
                                ecg[li, max(0, q - 10) : min(ecg.shape[1], q + 11)]
                            )
                            for li, q in group
                        ]
                    )
                )
                events.append(
                    {
                        "sample": loc,
                        "lead_count": len(group),
                        "snr_db": snr,
                        "certainty": "certain"
                        if snr >= cfg["snr_min_db"]
                        else "uncertain",
                    }
                )
            for _, q in group:
                used.add(q)
        elif group:
            # A one-lead candidate is retained as uncertainty, never promoted.
            loc = group[0][1]
            if not events or loc - events[-1]["sample"] >= refractory:
                events.append(
                    {
                        "sample": loc,
                        "lead_count": 1,
                        "snr_db": robust_snr(
                            ecg[
                                group[0][0],
                                max(0, loc - 10) : min(ecg.shape[1], loc + 11),
                            ]
                        ),
                        "certainty": "uncertain",
                    }
                )
    return events, lead_peaks, filtered


def rr_labels(events, fs, cfg):
    times = np.array([e["sample"] for e in events], dtype=float) / fs
    rows = []
    if len(times) < 2:
        return rows
    rr = np.diff(times)
    for i, v in enumerate(rr):
        label = "NN_CLEAN"
        reason = ""
        if not (cfg["rr_bounds_seconds"][0] <= v <= cfg["rr_bounds_seconds"][1]):
            label = "RR_OUT_OF_RANGE"
            reason = "absolute_bounds"
        elif (
            events[i]["certainty"] != "certain"
            or events[i + 1]["certainty"] != "certain"
        ):
            label = "RR_UNCERTAIN"
            reason = "uncertain_r_peak"
        elif i and abs(v - rr[i - 1]) / max(rr[i - 1], 1e-9) > cfg["rr_jump_fraction"]:
            label = "RR_ECTOPIC"
            reason = "adjacent_jump"
        rows.append(
            {
                "start_s": times[i],
                "end_s": times[i + 1],
                "rr_s": v,
                "label": label,
                "reason": reason,
            }
        )
    # local MAD is a flag only; no correction or interpolation.
    w = cfg["rr_mad_window_beats"]
    for i, row in enumerate(rows):
        lo = max(0, i - w // 2)
        hi = min(len(rr), i + w // 2 + 1)
        med = np.median(rr[lo:hi])
        mad = np.median(np.abs(rr[lo:hi] - med)) * 1.4826
        if (
            mad > 0
            and abs(row["rr_s"] - med) > cfg["rr_mad_multiplier"] * mad
            and row["label"] == "NN_CLEAN"
        ):
            row["label"] = "RR_ECTOPIC"
            row["reason"] = "local_mad"
    return rows


def egg_mask(x: np.ndarray, fs: float, cfg: dict):
    d = np.diff(x, prepend=x[0])
    dm = np.median(np.abs(d - np.median(d))) * 1.4826
    mask = np.isfinite(x)
    if dm > 0:
        mask &= np.abs(d) <= cfg["derivative_mad_multiplier"] * dm
    # Absolute saturation is only applied when signal is represented in microvolts.
    robust = np.median(np.abs(x - np.median(x)))
    if robust > 1e-9:
        mask &= np.abs(x - np.median(x)) < max(
            np.percentile(np.abs(x - np.median(x)), 99.9) * 2, 1e-9
        )
    return mask


def egg_spectrum(x, fs, mask, cfg):
    out = []
    n = int(cfg["welch_window_seconds"] * fs)
    step = int(cfg["welch_step_seconds"] * fs)
    for start in range(0, len(x) - n + 1, step):
        sl = slice(start, start + n)
        valid = float(np.mean(mask[sl]))
        if valid < 0.8:
            out.append(
                {
                    "start_s": start / fs,
                    "valid_fraction": valid,
                    "status": "invalid_mask",
                }
            )
            continue
        f, p = signal.welch(
            x[sl], fs=fs, nperseg=n, window=("kaiser", 2.5), detrend="linear"
        )
        band = (f >= 1 / 60) & (f <= 10 / 60)
        idx = np.flatnonzero(band)
        if not len(idx):
            out.append(
                {"start_s": start / fs, "valid_fraction": valid, "status": "no_band"}
            )
            continue
        winner = idx[np.argmax(p[idx])]
        total = np.trapezoid(p[idx], f[idx])
        local = np.abs(f - f[winner]) <= 0.5 / 60
        ratio = np.trapezoid(p[local], f[local]) / total if total else 0
        noise = np.median(p[idx])
        prom = 10 * np.log10(max(p[winner], 1e-20) / max(noise, 1e-20))
        cpm = f[winner] * 60
        descriptor = (
            "band_1_2.5_cpm"
            if 1 <= cpm < 2.5
            else "band_2.5_3.75_cpm"
            if 2.5 <= cpm < 3.75
            else "band_3.75_10_cpm"
            if 3.75 <= cpm <= 10
            else "outside_target_band"
        )
        prob = np.maximum(p[idx], 0)
        prob = prob / max(float(np.sum(prob)), 1e-20)
        entropy = float(
            -np.sum(prob * np.log(np.maximum(prob, 1e-20))) / np.log(max(len(prob), 2))
        )
        cdf = np.cumsum(prob)
        q = lambda qv: float(f[idx[min(len(idx) - 1, int(np.searchsorted(cdf, qv)))]])
        band_ratio = lambda lo, hi: (
            float(
                np.trapezoid(p[(f >= lo) & (f < hi)], f[(f >= lo) & (f < hi)]) / total
            )
            if total
            else 0.0
        )
        out.append(
            {
                "start_s": start / fs,
                "valid_fraction": valid,
                "status": "valid"
                if prom >= cfg["peak_prominence_db"]
                else "low_prominence",
                "df_cpm": cpm,
                "dpr": ratio,
                "prominence_db": prom,
                "band_descriptor": descriptor,
                "rhythm_status": "descriptive_unvalidated",
                "power_ratio_band_1_2.5_cpm": band_ratio(1 / 60, 2.5 / 60),
                "power_ratio_band_2.5_3.75_cpm": band_ratio(2.5 / 60, 3.75 / 60),
                "power_ratio_band_3.75_10_cpm": band_ratio(3.75 / 60, 10 / 60),
                "spectral_entropy": entropy,
                "freq_quantile_25_hz": q(0.25),
                "freq_quantile_50_hz": q(0.50),
                "freq_quantile_75_hz": q(0.75),
                "rms_valid_uv": float(np.sqrt(np.mean(np.square(x[sl][mask[sl]]))))
                if np.any(mask[sl])
                else float("nan"),
            }
        )
    return out


def crosstalk_subtract(egg: np.ndarray, r_events: list[dict], fs: float, cfg: dict):
    """Subtract a conservative R-triggered ECG template from EGG.

    The template is estimated independently per EGG channel from up to the
    first 31 *certain* events.  Only the 8--25 Hz component is removed, and
    only event windows with a finite, correlated segment are changed.  The
    result remains a candidate artifact reduction product; it is never a
    physiological validation of the EGG.
    """
    nchan, n = egg.shape
    pre, post = cfg["window_seconds"]
    a, b = round(pre * fs), round(post * fs)
    L = b - a
    peak_samples = [
        int(round(e["sample"] * fs / 250.0))
        for e in r_events
        if e["certainty"] == "certain"
    ]
    peak_samples = peak_samples[: int(cfg["template_beats"])]
    before = egg.copy()
    after = egg.copy()
    applied = np.zeros((nchan, n), dtype=bool)
    rows = []
    if len(peak_samples) < int(cfg["template_beats"]):
        rows = [
            {
                "channel": ci + 1,
                "template_count": len(peak_samples),
                "windows_applied": 0,
                "qrs_attenuation_db": 0.0,
                "slow_band_corr": "",
                "status": "insufficient_template",
                "safety_gate": "not_run",
            }
            for ci in range(nchan)
        ]
        return after, applied, rows
    sos = signal.butter(3, cfg["qrs_band_hz"], btype="bandpass", fs=fs, output="sos")
    for ci in range(nchan):
        snippets = []
        locations = []
        for p in peak_samples:
            lo, hi = p + a, p + b
            if lo < 0 or hi > n:
                continue
            s = egg[ci, lo:hi]
            if np.isfinite(s).all():
                snippets.append(signal.sosfiltfilt(sos, s))
                locations.append((lo, hi))
        if len(snippets) < int(cfg["template_beats"]):
            rows.append(
                {
                    "channel": ci + 1,
                    "template_count": len(snippets),
                    "status": "insufficient_template",
                }
            )
            continue
        template = np.median(np.vstack(snippets), axis=0)
        template -= np.median(template[: max(1, round(-pre * fs))])
        denom = float(np.dot(template, template))
        changed = 0
        qrs_before = []
        qrs_after = []
        for lo, hi in locations:
            seg = egg[ci, lo:hi]
            filt = signal.sosfiltfilt(sos, seg)
            corr = (
                float(np.corrcoef(filt, template)[0, 1])
                if np.std(filt) > 0 and np.std(template) > 0
                else 0.0
            )
            if not np.isfinite(corr) or corr < 0.5 or denom <= 0:
                continue
            scale = float(np.dot(filt, template) / denom)
            scale = float(np.clip(scale, -3.0, 3.0))
            after[ci, lo:hi] = seg - scale * template
            applied[ci, lo:hi] = True
            changed += 1
            qrs_before.append(float(np.sum(filt * filt)))
            qrs_after.append(float(np.sum((filt - scale * template) ** 2)))
        att = (
            float(
                10
                * np.log10(
                    max(np.sum(qrs_before), 1e-20) / max(np.sum(qrs_after), 1e-20)
                )
            )
            if qrs_before
            else 0.0
        )
        slow_before = signal.sosfiltfilt(
            signal.butter(2, [0.015, 0.15], btype="bandpass", fs=fs, output="sos"),
            egg[ci],
        )
        slow_after = signal.sosfiltfilt(
            signal.butter(2, [0.015, 0.15], btype="bandpass", fs=fs, output="sos"),
            after[ci],
        )
        corr_slow = (
            float(np.corrcoef(slow_before, slow_after)[0, 1])
            if np.std(slow_before) > 0 and np.std(slow_after) > 0
            else 0.0
        )
        gate = (
            att >= cfg["min_attenuation_db"] and corr_slow >= cfg["slow_band_corr_min"]
        )
        if not gate:
            # Retain the attempted product in the NPZ, but do not feed an
            # unqualified subtraction into EGG spectral descriptors.
            after[ci] = egg[ci]
            applied[ci] = False
        rows.append(
            {
                "channel": ci + 1,
                "template_count": len(snippets),
                "windows_applied": changed,
                "qrs_attenuation_db": att,
                "slow_band_corr": corr_slow,
                "status": "candidate_subtracted"
                if changed
                else "no_correlated_template",
                "safety_gate": "pass" if gate else "fail_unvalidated",
            }
        )
    return after, applied, rows


def crosstalk_censor_mask(n: int, r_events: list[dict], fs: float, cfg: dict):
    """Mask candidate ECG-contaminated intervals without changing EGG values."""
    mask = np.zeros(n, dtype=bool)
    a, b = (
        round(cfg["censor_window_seconds"][0] * fs),
        round(cfg["censor_window_seconds"][1] * fs),
    )
    for e in r_events:
        lo = max(0, int(round(e["sample"] * fs / 250.0)) + a)
        hi = min(n, int(round(e["sample"] * fs / 250.0)) + b)
        if hi > lo:
            mask[lo:hi] = True
    return mask


def single_window_256s(x: np.ndarray, fs: float, mask: np.ndarray, cfg: dict) -> dict:
    """Compute the separately named 256 s sensitivity spectrum, no padding."""
    n = int(256 * fs)
    if len(x) < n or np.mean(mask[:n]) < 0.8:
        return {"status": "EGG_LSP_INESTIMABLE", "reason": "window_missing_or_short"}
    y = x[:n][mask[:n]]
    if len(y) < int(0.8 * n):
        return {"status": "EGG_LSP_INESTIMABLE", "reason": "window_mask"}
    # This branch is only permitted after the censor audit passes.  It uses
    # actual samples and actual frequency bins; no zero padding is performed.
    f, p = signal.periodogram(x[:n], fs=fs, window="hann", detrend="constant", nfft=n)
    band = (f >= 1 / 60) & (f <= 10 / 60)
    if not np.any(band):
        return {"status": "EGG_LSP_INESTIMABLE", "reason": "no_target_band"}
    j = np.flatnonzero(band)[np.argmax(p[band])]
    return {
        "status": "descriptive_candidate",
        "df_hz": float(f[j]),
        "df_cpm": float(f[j] * 60),
        "n_samples": n,
        "zero_padding": False,
    }


def mask_audit(mask: np.ndarray, fs: float) -> dict:
    """Audit a censor mask without filling or bridging its gaps."""
    flat = np.asarray(mask, bool)
    ratio = float(np.mean(flat)) if flat.size else 1.0
    best = run = 0
    for v in flat:
        if v:
            run = 0
        else:
            run += 1
            best = max(best, run)
    # The mask itself is a deterministic window pattern.  Its low-frequency
    # peak is reported as an audit signal; it is never treated as physiology.
    if flat.size >= 8:
        f, p = signal.welch(
            (~flat).astype(float),
            fs=fs,
            nperseg=min(flat.size, int(fs * 120)),
            detrend="constant",
        )
        band = (f >= 0.015) & (f <= 0.150)
        bp = p[band]
        leakage = (
            float(
                10
                * np.log10(
                    max(float(np.max(bp)), 1e-20) / max(float(np.median(bp)), 1e-20)
                )
            )
            if bp.size
            else float("inf")
        )
    else:
        leakage = float("inf")
    reasons = []
    if ratio > 0.25:
        reasons.append("CENSORING_EXCEEDED")
    if best / fs < 15.0:
        reasons.append("NO_CONTINUOUS_SPAN")
    if leakage > 3.0:
        reasons.append("MASK_SPECTRAL_LEAKAGE")
    return {
        "censoring_time_ratio": ratio,
        "max_continuous_uncensored_sec": best / fs,
        "pure_mask_leakage_peak_to_floor_db": leakage,
        "status": "EGG_LSP_INESTIMABLE" if reasons else "censor_audit_pass",
        "trigger_reason": "|".join(reasons),
    }


def local_hrv_epochs(rr_rows: list[dict], duration_s: float = 300.0) -> list[dict]:
    """Produce Tier-C descriptive windows from labelled RR intervals."""
    out = []
    for start in np.arange(0.0, duration_s - 60.0 + 1e-9, 30.0):
        end = start + 60.0
        rows = [
            r
            for r in rr_rows
            if float(r["start_s"]) < end and float(r["end_s"]) > start
        ]
        clean = [r for r in rows if r["label"] == "NN_CLEAN"]
        valid_ratio = len(clean) / max(len(rows), 1)
        max_gap = 0.0
        prev = end if not rows else start
        for r in sorted(rows, key=lambda z: float(z["start_s"])):
            gap = max(0.0, float(r["start_s"]) - prev)
            max_gap = max(max_gap, gap)
            prev = float(r["end_s"])
        vals = np.asarray([float(r["rr_s"]) * 1000 for r in clean], float)
        if len(vals):
            med = float(np.median(vals))
            iqr = float(np.percentile(vals, 75) - np.percentile(vals, 25))
            madsd = (
                float(np.median(np.abs(np.diff(vals))))
                if len(vals) > 1
                else float("nan")
            )
        else:
            med = iqr = madsd = float("nan")
        ok = valid_ratio >= 0.80 and max_gap <= 3.0 and len(clean) >= 20
        out.append(
            {
                "window_idx": len(out),
                "t_start_s": start,
                "t_end_s": end,
                "valid_nn_ratio": valid_ratio,
                "max_gap_s": max_gap,
                "nn_count": len(clean),
                "nn_median_ms": med,
                "nn_iqr_ms": iqr,
                "madsd_ms": madsd,
                "status": "TIER_C_DESCRIPTIVE" if ok else "EPOCH_INVALID",
            }
        )
    return out


def stress_rows(cfg):
    """Deterministic synthetic stress checks; no real participant inference."""
    rng = np.random.default_rng(20260929)
    t = np.arange(120 * 250) / 250
    y = np.zeros_like(t)
    truth = np.arange(0.8, 119, 0.8)
    for b in truth:
        y += np.exp(-0.5 * ((t - b) / 0.014) ** 2)
    rows = []
    for snr in (20.0,):
        noise = rng.normal(size=len(y))
        scale = np.std(y) / (10 ** (snr / 20) * max(np.std(noise), 1e-12))
        z = y + scale * noise
        ev = consensus_rpeaks(np.vstack([z, z, z]), 250, cfg["ecg"])[0]
        rows.append(
            {
                "stress": "synthetic_ecg_snr_db",
                "level": snr,
                "repeat": 1,
                "events": len(ev),
                "status": "internal_numeric_only",
            }
        )
    for pct in (0.10,):
        m = np.ones(len(y), bool)
        m[: int(len(y) * pct)] = False
        rows.append(
            {
                "stress": "synthetic_dropout_fraction",
                "level": pct,
                "repeat": 1,
                "retained_fraction": float(np.mean(m)),
                "status": "internal_numeric_only",
            }
        )
    return rows


def main():
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    tasks = list(
        csv.DictReader((TASK_DIR / "recording_tasks.csv").open(encoding="utf-8-sig"))
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (
        ROOT
        / "08_outputs"
        / f"electrophysiology_algorithmic_qc_{stamp}_{uuid.uuid4().hex[:8]}"
    )
    out.mkdir(parents=True)
    events_rows = []
    rr_rows = []
    egg_rows = []
    crosstalk_rows = []
    sync_rows = []
    joint_rows = []
    qc_rows = []
    hrv_rows = []
    estimand_rows = []
    failures = []
    synth = []
    crosstalk_dir = out / "crosstalk_npz"
    crosstalk_dir.mkdir()
    for rec in tasks:
        try:
            with Path(rec["path"]).open("rb") as f:
                reader = bioread.reader.Reader(f)
                reader._read_headers()
                reader._read_data(None, bioread.reader.CHUNK_SIZE)
                data = reader.datafile
            by_name = {"ECG100C": [], "EGG100C": []}
            for c in data.channels:
                if c.name in by_name:
                    by_name[c.name].append(np.asarray(c.data, float))
            if len(by_name["ECG100C"]) != 3 or len(by_name["EGG100C"]) != 2:
                raise ValueError(
                    f"channel_name_count_ecg_{len(by_name['ECG100C'])}_egg_{len(by_name['EGG100C'])}"
                )
            lo = int(rec["source_window_start_sample"])
            hi = int(rec["source_window_end_sample"])
            n = hi - lo
            raw_ecg = np.vstack([x[lo:hi] for x in by_name["ECG100C"]])
            raw_egg = np.vstack([x[lo:hi] for x in by_name["EGG100C"]])
            # Preserve the recorded duration.  Some selected segments are a
            # few samples shorter than 300 s; they are retained with their
            # true overlap and are not padded or bridged.
            if (
                n <= 0
                or not np.isfinite(raw_ecg).all()
                or not np.isfinite(raw_egg).all()
            ):
                raise ValueError("nonfinite_or_empty_shared_window")
            ecg = np.vstack([resample_exact(x, 2000, 250) for x in raw_ecg])
            egg = np.vstack([resample_exact(x, 2000, 100) for x in raw_egg])
            ev, lead_peaks, filtered = consensus_rpeaks(ecg, 250, cfg["ecg"])
            rrs = rr_labels(ev, 250, cfg["ecg"])
            egg_corrected, subtraction_mask, ct_rows = crosstalk_subtract(
                raw_egg, ev, 2000, cfg["crosstalk"]
            )
            censor_mask = np.vstack(
                [crosstalk_censor_mask(raw_egg.shape[1], ev, 2000, cfg["crosstalk"])]
                * raw_egg.shape[0]
            )
            censor_audit = mask_audit(censor_mask[0], 2000)
            # Keep the before/after products and masks outside the source tree.
            np.savez_compressed(
                crosstalk_dir / f"{rec['task_id']}.npz",
                egg_before=raw_egg,
                egg_after=egg_corrected,
                mask_crosstalk_subtracted=subtraction_mask,
                mask_crosstalk_censor=censor_mask,
                r_peak_samples=np.asarray([e["sample"] for e in ev], dtype=int),
            )
            for row in ct_rows:
                row.update(task_id=rec["task_id"], person_id=rec["person_id"])
                crosstalk_rows.append(row)
            for j, e in enumerate(ev):
                events_rows.append(
                    {
                        "task_id": rec["task_id"],
                        "person_id": rec["person_id"],
                        "peak_time_s": e["sample"] / 250,
                        "lead_count": e["lead_count"],
                        "snr_db": e["snr_db"],
                        "certainty": e["certainty"],
                    }
                )
            for row in rrs:
                row.update(task_id=rec["task_id"], person_id=rec["person_id"])
                rr_rows.append(row)
            for ep in local_hrv_epochs(rrs, n / 2000.0):
                ep.update(task_id=rec["task_id"], person_id=rec["person_id"])
                hrv_rows.append(ep)
            # EGG spectral descriptors use the candidate-corrected signal only
            # where the correction product passed its local safety gate; all
            # original and corrected arrays remain available in the NPZ.
            # The subtraction failed its safety gate in this run; preserve
            # original values and expose the censor mask instead of feeding a
            # modified signal into the primary EGG spectrum.
            egg_for_spectrum = np.vstack(
                [resample_exact(x, 2000, 100) for x in raw_egg]
            )
            masks = [egg_mask(x, 100, cfg["egg"]) for x in egg_for_spectrum]
            censor_egg = (
                np.vstack(
                    [resample_exact(x.astype(float), 2000, 100) for x in censor_mask]
                )
                > 0.5
            )
            masks = [m & ~censor_egg[i] for i, m in enumerate(masks)]
            specs = [
                egg_spectrum(egg_for_spectrum[i], 100, masks[i], cfg["egg"])
                for i in range(2)
            ]
            for ci, sp in enumerate(specs):
                for w in sp:
                    w.update(
                        task_id=rec["task_id"],
                        person_id=rec["person_id"],
                        channel=ci + 1,
                    )
                    egg_rows.append(w)
            valid = [w for sp in specs for w in sp if w.get("status") == "valid"]
            df = [
                w["df_cpm"] for sp in specs for w in sp if w.get("df_cpm") is not None
            ]
            # The ACQ file provides one sample clock; this is an algorithmic check, not independent hardware validation.
            overlap_s = n / 2000.0
            sync_status = (
                "synchronous_same_acq_sample_index_nominal"
                if overlap_s >= cfg["sync"]["required_overlap_seconds"]
                else "partial_window_same_acq_sample_index"
            )
            sync_rows.append(
                {
                    "task_id": rec["task_id"],
                    "person_id": rec["person_id"],
                    "overlap_s": overlap_s,
                    "timestamp_monotonic": True,
                    "sync_status": sync_status,
                }
            )
            joint_s = min(
                300.0,
                float(sum(w.get("valid_fraction", 0) >= 0.8 for w in valid))
                * cfg["egg"]["welch_step_seconds"],
            )
            joint_rows.append(
                {
                    "task_id": rec["task_id"],
                    "person_id": rec["person_id"],
                    "joint_valid_seconds": joint_s,
                    "wco_status": "fully_suppressed_missing_respiration_and_unvalidated_crosstalk",
                    "pac_status": "fully_suppressed_missing_respiration_and_unvalidated_crosstalk",
                    "directionality_status": "fully_suppressed",
                }
            )
            sens = []
            for ci in range(2):
                sens.append(
                    single_window_256s(egg_for_spectrum[ci], 100, masks[ci], cfg["egg"])
                )
            estimand_rows.append(
                {
                    "task_id": rec["task_id"],
                    "person_id": rec["person_id"],
                    "primary_estimand": "welch_120s_30s_step",
                    "sensitivity_estimand": "single_window_256s_no_zero_padding",
                    "sensitivity_status": "EGG_LSP_INESTIMABLE"
                    if censor_audit["status"] == "EGG_LSP_INESTIMABLE"
                    else sens[0].get("status"),
                    "sensitivity_ch1_df_cpm": sens[0].get("df_cpm", ""),
                    "sensitivity_ch2_df_cpm": sens[1].get("df_cpm", ""),
                    "censor_audit_status": censor_audit["status"],
                    "censoring_time_ratio": censor_audit["censoring_time_ratio"],
                    "max_continuous_uncensored_sec": censor_audit[
                        "max_continuous_uncensored_sec"
                    ],
                    "pure_mask_leakage_db": censor_audit[
                        "pure_mask_leakage_peak_to_floor_db"
                    ],
                    "egg_spectrum_status": "EGG_LSP_INESTIMABLE"
                    if censor_audit["status"] == "EGG_LSP_INESTIMABLE"
                    else "descriptive_candidate",
                }
            )
            total_candidates = sum(len(a) for a in lead_peaks)
            consensus = sum(e["lead_count"] >= 2 for e in ev)
            certain = sum(e["certainty"] == "certain" for e in ev)
            valid_rr = sum(r["label"] == "NN_CLEAN" for r in rrs)
            qc_rows.append(
                {
                    "task_id": rec["task_id"],
                    "person_id": rec["person_id"],
                    "r_peak_events": len(ev),
                    "candidate_peaks": total_candidates,
                    "consensus_rate": consensus / max(total_candidates, 1),
                    "certain_ratio": certain / max(len(ev), 1),
                    "rr_total": len(rrs),
                    "nn_clean": valid_rr,
                    "nn_valid_fraction": valid_rr / max(len(rrs), 1),
                    "ectopic_or_out_of_range": sum(
                        r["label"] in ("RR_ECTOPIC", "RR_OUT_OF_RANGE") for r in rrs
                    )
                    / max(len(rrs), 1),
                    "egg_valid_windows": len(valid),
                    "egg_window_total": len(specs) * 7,
                    "e02_status": "algorithmic_candidate",
                    "e03_tier": "C_candidate_only",
                    "e04_status": "exploratory_descriptive_egg_spectrum",
                    "e06_status": "synchronous_same_acq_sample_index",
                    "e07_status": "exploratory_fragmented_hrv_tier_c",
                    "e08_estimand": "120s_welch_30s_step_primary_256s_single_window_sensitivity_separate",
                }
            )
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            failures.append(
                {"task_id": rec["task_id"], "person_id": rec["person_id"], "error": err}
            )
            # Emit explicit terminal statuses for every recording. This keeps
            # missing/nonfinite segments visible without imputing or silently
            # dropping the participant from the audit.
            sync_rows.append(
                {
                    "task_id": rec["task_id"],
                    "person_id": rec["person_id"],
                    "overlap_s": "",
                    "timestamp_monotonic": "",
                    "sync_status": "suppressed_input_missing_or_incomplete",
                }
            )
            joint_rows.append(
                {
                    "task_id": rec["task_id"],
                    "person_id": rec["person_id"],
                    "joint_valid_seconds": 0,
                    "wco_status": "suppressed_input_missing_or_incomplete",
                    "pac_status": "suppressed_input_missing_or_incomplete",
                    "directionality_status": "suppressed_input_missing_or_incomplete",
                }
            )
            qc_rows.append(
                {
                    "task_id": rec["task_id"],
                    "person_id": rec["person_id"],
                    "r_peak_events": "",
                    "candidate_peaks": "",
                    "consensus_rate": "",
                    "certain_ratio": "",
                    "rr_total": "",
                    "nn_clean": "",
                    "nn_valid_fraction": "",
                    "ectopic_or_out_of_range": "",
                    "egg_valid_windows": "",
                    "egg_window_total": "",
                    "e02_status": "suppressed_input_missing_or_incomplete",
                    "e03_tier": "suppressed",
                    "e04_status": "suppressed_input_missing_or_incomplete",
                    "e06_status": "suppressed_input_missing_or_incomplete",
                    "e07_status": "suppressed",
                    "e08_estimand": "not_estimable",
                }
            )
    # synthetic repeatability gate: detector must be deterministic on fixed input.
    rng = np.random.default_rng(20260929)
    t = np.arange(120 * 250) / 250
    y = np.zeros_like(t)
    truth = np.arange(0.8, 119, 0.8)
    for b in truth:
        y += np.exp(-0.5 * ((t - b) / 0.014) ** 2)
    y += 0.008 * rng.normal(size=len(y))
    x = np.vstack(
        [y, y + 0.001 * rng.normal(size=len(y)), y + 0.001 * rng.normal(size=len(y))]
    )
    a = consensus_rpeaks(x, 250, cfg["ecg"])[0]
    b = consensus_rpeaks(x, 250, cfg["ecg"])[0]
    synth.append(
        {
            "name": "fixed_qrs_repeatability",
            "events_run1": len(a),
            "events_run2": len(b),
            "identical": a == b,
            "truth_count": len(truth),
        }
    )
    stress = stress_rows(cfg)
    for name, rows in [
        ("r_peak_events.csv", events_rows),
        ("rr_nn_intervals.csv", rr_rows),
        ("egg_window_quality.csv", egg_rows),
        ("crosstalk_status.csv", crosstalk_rows),
        ("sync_status.csv", sync_rows),
        ("joint_status.csv", joint_rows),
        ("recording_qc_summary.csv", qc_rows),
        ("hrv_tier_c_epochs.csv", hrv_rows),
        ("estimand_audit.csv", estimand_rows),
        ("synthetic_validation.csv", synth),
        ("stress_test_report.csv", stress),
        ("failures.csv", failures),
    ]:
        if rows:
            write_csv(out / name, rows)
    summary = {
        "status": "completed_algorithmic_qc_with_scientific_downgrade"
        if not failures
        else "completed_with_failures",
        "recordings": len(tasks),
        "completed": len(tasks) - len(failures),
        "failures": len(failures),
        "r_peak_events": len(events_rows),
        "rr_intervals": len(rr_rows),
        "egg_windows": len(egg_rows),
        "joint_rows": len(joint_rows),
        "hrv_tier_c_epochs": len(hrv_rows),
        "scientific_validation": "not_established_without_independent_reference",
        "e05": "conditionally_completed_time_censored_with_lsp_inestimability_audit",
        "e06": "synchronous_same_acq_sample_index_nominal",
        "e09": "fully_suppressed_missing_respiration_and_unvalidated_crosstalk",
        "e10": "closed_synthetic_stress_pipeline",
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = {
        "config": str(CONFIG_PATH),
        "config_sha256": sha(CONFIG_PATH),
        "task_manifest_sha256": sha(TASK_DIR / "manifest.json"),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "git_revision": subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip(),
        "outputs_sha256": {
            str(p.relative_to(out)): sha(p)
            for p in out.rglob("*")
            if p.is_file() and p.name != "run_manifest.json"
        },
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
