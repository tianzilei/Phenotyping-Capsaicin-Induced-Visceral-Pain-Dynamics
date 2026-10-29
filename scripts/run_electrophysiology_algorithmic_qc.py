"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import csv
from pathlib import Path
import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]


def write_csv(path: Path, rows: list[dict]):
    fields = list(dict.fromkeys((k for row in rows for k in row))) if rows else []
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
    return (peaks.astype(int), y)


def consensus_rpeaks(ecg: np.ndarray, fs: float, cfg: dict):
    lead_peaks = []
    filtered = []
    for x in ecg:
        p, y = detect_lead(x, fs, cfg)
        lead_peaks.append(p)
        filtered.append(y)
    tol = round(cfg["consensus_tolerance_seconds"] * fs)
    refractory = round(cfg["refractory_seconds"] * fs)
    all_events = sorted(set((int(p) for arr in lead_peaks for p in arr)))
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
    return (events, lead_peaks, filtered)


def rr_labels(events, fs, cfg):
    times = np.array([e["sample"] for e in events], dtype=float) / fs
    rows = []
    if len(times) < 2:
        return rows
    rr = np.diff(times)
    for i, v in enumerate(rr):
        label = "NN_CLEAN"
        reason = ""
        if not cfg["rr_bounds_seconds"][0] <= v <= cfg["rr_bounds_seconds"][1]:
            label = "RR_OUT_OF_RANGE"
            reason = "absolute_bounds"
        elif (
            events[i]["certainty"] != "certain"
            or events[i + 1]["certainty"] != "certain"
        ):
            label = "RR_UNCERTAIN"
            reason = "uncertain_r_peak"
        elif i and abs(v - rr[i - 1]) / max(rr[i - 1], 1e-09) > cfg["rr_jump_fraction"]:
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
    w = cfg["rr_mad_window_beats"]
    for i, row in enumerate(rows):
        lo = max(0, i - w // 2)
        hi = min(len(rr), i + w // 2 + 1)
        med = np.median(rr[lo:hi])
        mad = np.median(np.abs(rr[lo:hi] - med)) * 1.4826
        if (
            mad > 0
            and abs(row["rr_s"] - med) > cfg["rr_mad_multiplier"] * mad
            and (row["label"] == "NN_CLEAN")
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
    robust = np.median(np.abs(x - np.median(x)))
    if robust > 1e-09:
        mask &= np.abs(x - np.median(x)) < max(
            np.percentile(np.abs(x - np.median(x)), 99.9) * 2, 1e-09
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
                "freq_quantile_50_hz": q(0.5),
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
    a, b = (round(pre * fs), round(post * fs))
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
        return (after, applied, rows)
    sos = signal.butter(3, cfg["qrs_band_hz"], btype="bandpass", fs=fs, output="sos")
    for ci in range(nchan):
        snippets = []
        locations = []
        for p in peak_samples:
            lo, hi = (p + a, p + b)
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
    return (after, applied, rows)


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
    if flat.size >= 8:
        f, p = signal.welch(
            (~flat).astype(float),
            fs=fs,
            nperseg=min(flat.size, int(fs * 120)),
            detrend="constant",
        )
        band = (f >= 0.015) & (f <= 0.15)
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
    for start in np.arange(0.0, duration_s - 60.0 + 1e-09, 30.0):
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
        ok = valid_ratio >= 0.8 and max_gap <= 3.0 and (len(clean) >= 20)
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
    for pct in (0.1,):
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
