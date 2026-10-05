"""Exact-rate anti-alias resampling and descriptive spectra, without artifact acceptance."""

from math import gcd
import numpy as np
from scipy import signal


def resample_exact(x, source_rate, target_rate, beta=8.6):
    x = np.asarray(x, dtype=float)
    if x.ndim != 1 or len(x) < 2 or not np.isfinite(x).all():
        raise ValueError("Finite one-dimensional vector required; no gap filling")
    if (
        source_rate != int(source_rate)
        or target_rate != int(target_rate)
        or not 0 < target_rate <= source_rate
    ):
        raise ValueError("Positive integer rates and downsampling required")
    common = gcd(int(source_rate), int(target_rate))
    return signal.resample_poly(
        x,
        int(target_rate) // common,
        int(source_rate) // common,
        window=("kaiser", beta),
        padtype="line",
    )


def band_area(f, psd, low, high):
    if not f[0] <= low < high <= f[-1]:
        raise ValueError("Band outside frequency support")
    inside = (f > low) & (f < high)
    grid = np.r_[low, f[inside], high]
    values = np.r_[np.interp(low, f, psd), psd[inside], np.interp(high, f, psd)]
    return float(np.trapezoid(values, grid))


def welch_description(x, rate, seconds):
    n = int(rate * seconds)
    if len(x) < n or not np.isfinite(x).all():
        raise ValueError("Insufficient finite samples for specified spectral segment")
    f, p = signal.welch(
        x,
        fs=rate,
        window="hann",
        nperseg=n,
        noverlap=n // 2,
        nfft=n,
        detrend="linear",
        scaling="density",
        average="mean",
    )
    return f, p, 1 + (len(x) - n) // (n - n // 2)


def window_spectrum(raw, label, cfg):
    raw = np.asarray(raw)
    if len(raw) != cfg["window_seconds"] * cfg["input_rate_hz"]:
        raise ValueError("Only complete fixed windows accepted")
    if not np.isfinite(raw).all():
        return {"spectral_status": "nonfinite_raw_no_fill"}, None
    if np.all(raw == raw[0]):
        return {"spectral_status": "constant_raw_no_ratio"}, None
    source = cfg["input_rate_hz"]
    beta = cfg["resample_kaiser_beta"]
    if label == "EGG100C":
        y = raw
        for target in cfg["egg_resampling_stages_hz"]:
            y = resample_exact(y, source, target, beta)
            source = target
        rate = cfg["egg_rate_hz"]
        segment = cfg["egg_segment_seconds"]
    elif label == "ECG100C":
        rate = cfg["ecg_rate_hz"]
        segment = cfg["ecg_segment_seconds"]
        y = resample_exact(raw, source, rate, beta)
    else:
        raise ValueError("Unsupported signal label")
    trim = cfg["edge_trim_seconds_each_side"] * rate
    y = y[trim:-trim] if trim else y
    f, p, count = welch_description(y, rate, segment)
    result = dict(
        spectral_status="computed_not_artifact_accepted",
        effective_rate_hz=rate,
        used_seconds=len(y) / rate,
        welch_segments=count,
        frequency_step_hz=float(f[1] - f[0]),
        rms_detrended_native=float(np.sqrt(np.mean(signal.detrend(y) ** 2))),
    )
    if label == "EGG100C":
        broad = band_area(f, p, *cfg["egg_broad_hz"])
        norm = band_area(f, p, *cfg["egg_norm_hz"])
        mask = (f >= cfg["egg_broad_hz"][0]) & (f <= cfg["egg_broad_hz"][1])
        peak = float(f[mask][np.argmax(p[mask])])
        f2, p2, n2 = welch_description(y, rate, cfg["egg_sensitivity_segment_seconds"])
        mask2 = (f2 >= cfg["egg_broad_hz"][0]) & (f2 <= cfg["egg_broad_hz"][1])
        result.update(
            broad_power_native2=broad,
            norm_power_native2=norm,
            norm_fraction=norm / broad if broad > 0 else None,
            band_max_hz=peak,
            band_max_cpm=peak * 60,
            band_max_boundary=bool(peak in (f[mask][0], f[mask][-1])),
            band_max_hz_64s=float(f2[mask2][np.argmax(p2[mask2])]),
            norm_fraction_64s=band_area(f2, p2, *cfg["egg_norm_hz"])
            / band_area(f2, p2, *cfg["egg_broad_hz"])
            if band_area(f2, p2, *cfg["egg_broad_hz"]) > 0
            else None,
        )
    else:
        result.update(
            ecg_band_power_native2=band_area(f, p, *cfg["ecg_band_hz"]),
            line_band_power_native2=band_area(f, p, *cfg["ecg_line_band_hz"]),
        )
    return result, (f, p)
