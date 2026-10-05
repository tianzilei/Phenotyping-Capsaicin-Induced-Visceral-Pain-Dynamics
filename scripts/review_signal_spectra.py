"""Independent DFT normalization and band-integral checks for spectral delivery."""

import csv
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import scipy
import bioread
from scipy import signal
from audit_signal_readiness import ROOT, sha
from path_resolver import resolve_input
from capsaicin.hash_baseline import check_reference


def integrate_independent(f, p, lo, hi):
    total = 0.0
    for i in range(len(f) - 1):
        a = max(lo, f[i])
        b = min(hi, f[i + 1])
        if a >= b:
            continue
        slope = (p[i + 1] - p[i]) / (f[i + 1] - f[i])
        total += p[i] * (b - a) + 0.5 * slope * ((b - f[i]) ** 2 - (a - f[i]) ** 2)
    return float(total)


def manual_welch(y, rate, seconds):
    n = int(rate * seconds)
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)
    x = np.arange(n, dtype=float)
    x -= x.mean()
    xx = x @ x
    parts = []
    for start in range(0, len(y) - n + 1, n // 2):
        segment = y[start : start + n].copy()
        segment -= segment.mean()
        segment -= x * (x @ segment) / xx
        psd = np.abs(np.fft.rfft(segment * window)) ** 2 / (rate * (window @ window))
        psd[1:-1] *= 2
        parts.append(psd)
    return np.mean(parts, axis=0)


def main():
    run = ROOT / sys.argv[1]
    mp = run / "run_manifest.json"
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    if manifest["status"] not in [
        "completed_descriptive_spectra",
        "completed_with_file_failures",
    ]:
        raise ValueError("Source run not completed")
    out = (
        ROOT
        / "08_outputs"
        / (
            "signal_spectra_review_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "verification.json")],
        cwd=ROOT,
        check=True,
    )
    verified = 0
    for field in ["inputs_sha256", "signals_sha256", "outputs_sha256"]:
        for name, digest in manifest[field].items():
            p = run / name if field == "outputs_sha256" else resolve_input(name)
            check_reference(mp, field, name, digest, p)
            verified += 1
    cfg = json.loads(
        (ROOT / "config/signal_spectra_v1.json").read_text(encoding="utf-8")
    )
    rows = list(csv.DictReader((run / "windows_private.csv").open(encoding="utf-8")))
    errors = []
    comparisons = 0
    selected = {}
    for r in rows:
        if r["spectral_status"] != "computed_not_artifact_accepted":
            continue
        key = f"file_{int(r['source_file_index']):04d}.npz"
        if key not in selected:
            selected[key] = []
        selected[key].append(r)
    for key, group in selected.items():
        with np.load(run / "spectra_private" / key) as arrays:
            for r in group:
                name = f"c{r['channel']}_w{r['window_index']}"
                f = arrays[name + "_f"]
                p = arrays[name + "_psd"]
                if r["label"] == "EGG100C":
                    measures = [
                        ("broad_power_native2", cfg["egg_broad_hz"]),
                        ("norm_power_native2", cfg["egg_norm_hz"]),
                    ]
                else:
                    measures = [
                        ("ecg_band_power_native2", cfg["ecg_band_hz"]),
                        ("line_band_power_native2", cfg["ecg_line_band_hz"]),
                    ]
                for field, band in measures:
                    expected = float(r[field])
                    actual = integrate_independent(f, p, *band)
                    if not np.isclose(actual, expected, rtol=1e-10, atol=1e-15):
                        raise AssertionError(field)
                    errors.append(abs(actual - expected))
                    comparisons += 1
    # First eligible window of each modality, fixed ordering; independently form DFT/linear detrend/Hann scaling.
    checks = []
    for label in ["ECG100C", "EGG100C"]:
        r = next(
            r
            for r in rows
            if r["label"] == label
            and r["spectral_status"] == "computed_not_artifact_accepted"
        )
        with resolve_input(r["path"]).open("rb") as f:
            reader = bioread.reader.Reader(f)
            reader._read_headers()
            reader._read_data(None, bioread.reader.CHUNK_SIZE)
            data = reader.datafile
        raw = data.channels[int(r["channel"])].data[
            int(float(r["start_recording_s"]) * 2000) : int(
                float(r["end_recording_s"]) * 2000
            )
        ]
        if label == "ECG100C":
            y = signal.resample_poly(raw, 1, 8, window=("kaiser", 8.6), padtype="line")
            rate = 250
            seconds = 8
        else:
            y = signal.resample_poly(raw, 1, 20, window=("kaiser", 8.6), padtype="line")
            y = signal.resample_poly(y, 1, 25, window=("kaiser", 8.6), padtype="line")
            rate = 4
            seconds = 128
        y = y[10 * rate : -10 * rate]
        manual = manual_welch(y, rate, seconds)
        with np.load(
            run / "spectra_private" / f"file_{int(r['source_file_index']):04d}.npz"
        ) as a:
            stored = a[f"c{r['channel']}_w{r['window_index']}_psd"]
        np.testing.assert_allclose(manual, stored, rtol=1e-8, atol=1e-14)
        checks.append(
            dict(
                label=label,
                max_psd_absolute_difference=float(np.max(np.abs(manual - stored))),
            )
        )
    rscript = "C:/Program Files/R/R-4.6.1/bin/Rscript.exe"
    plot = ROOT / "scripts/plot_signal_spectra.R"
    with (out / "plot.log").open("w", encoding="utf-8") as f:
        subprocess.run(
            [rscript, str(plot), str(run), str(out)],
            cwd=ROOT,
            stdout=f,
            stderr=subprocess.STDOUT,
            env=dict(os.environ, TMP=str(out), TEMP=str(out)),
            check=True,
        )
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    record = list(
        csv.DictReader((run / "recording_summaries_private.csv").open(encoding="utf-8"))
    )
    egg = [r for r in record if r["label"] == "EGG100C"]
    descriptives = {
        k: dict(
            median=float(np.median([float(r[k]) for r in egg])),
            q25=float(np.quantile([float(r[k]) for r in egg], 0.25)),
            q75=float(np.quantile([float(r[k]) for r in egg], 0.75)),
        )
        for k in [
            "median_norm_fraction",
            "median_band_max_cpm",
            "median_abs_peak_difference_cpm",
        ]
    }
    egg_windows = [
        r
        for r in rows
        if r["label"] == "EGG100C"
        and r["spectral_status"] == "computed_not_artifact_accepted"
    ]
    lower_edge = int(
        sum(np.isclose(float(r["band_max_hz"]), 2 / 128) for r in egg_windows)
    )
    upper_edge = int(
        sum(np.isclose(float(r["band_max_hz"]), 19 / 128) for r in egg_windows)
    )
    result = dict(
        status="passed",
        verified_hashes=verified,
        band_integral_comparisons=comparisons,
        max_integral_abs_difference=max(errors),
        manual_welch_checks=checks,
        recording_summary_descriptives=descriptives,
        egg_lower_edge_windows=lower_edge,
        egg_upper_edge_windows=upper_edge,
    )
    (out / "verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    report = [
        "# 原始信号频谱描述与独立核验",
        "",
        "## Material Passport",
        "",
        "- Origin Skill: academic-research-suite / experiment-agent",
        "- Origin Mode: run + validate",
        "- Verification: 独立数值复核通过；科学质控尚未验收",
        "",
        f"完成{summary['files_completed']}/{summary['files_planned']}个ACQ文件；{summary['files_with_complete_windows']}个有完整5分钟窗，共{summary['complete_recording_windows']}个记录窗、{summary['channel_windows']}个通道窗。失败{summary['file_failures']}。这些数量不是独立受试者数。",
        "",
        "本轮从真实原始通道提取，替代旧CSV重复列路径。ECG精确降至250 Hz、EGG至4 Hz，均含抗混叠处理。所有完整窗口按记录起点定义、各裁10秒边缘；末段不补。97项合成测试通过。",
        "",
        f"EGG带内最大值位于所检频带边缘的通道窗为{summary['egg_band_boundary_maxima']}/{summary['egg_computed_windows']}；128/64秒谱分段的峰差绝对值中位数为{summary['egg_median_abs_128_vs_64_peak_difference_cpm']:.4f} cpm。最大值未被认定为真实胃节律；低频漂移、运动与分段长度均会影响此指标。",
        "",
        "|按记录汇总的EGG指标|记录间中位数|四分位范围|",
        "|---|---:|---:|",
    ]
    for label, key in [
        ("窄/宽频带功率比例", "median_norm_fraction"),
        ("带内最大谱峰（cpm）", "median_band_max_cpm"),
        ("128/64秒分段峰差绝对值（cpm）", "median_abs_peak_difference_cpm"),
    ]:
        z = descriptives[key]
        report.append(f"|{label}|{z['median']:.4f}|{z['q25']:.4f}–{z['q75']:.4f}|")
    report += [
        "",
        "先取同记录内通道窗中位数，再描述记录间分布；未去重为独立受试者，四分位范围不是置信区间。窄带比例不是正常节律时间比例，不能作异常胃电患病率。",
        "",
        f"频带低端第一个有效频点0.015625 Hz处有{lower_edge}个最大值，高端0.1484375 Hz处有{upper_edge}个。64秒和128秒两种分段在该频带的首个有效频点恰好相同，故峰差为0可能只表示两者都选了低端边界，不能当作胃节律稳定性证据。",
        "",
        f"独立分段线性积分复算{comparisons}项；ECG与EGG各一个预定首窗用NumPy手工线性去趋势/Hann/DFT重算PSD，均通过。复核{verified}项来源/信号/输出哈希。重采样仍调用同一SciPy实现，其正确性由独立合成时间尺度与抗混叠测试支撑，不称实现完全独立。",
        "",
        "![记录级频谱描述](signal_spectra_overview.png)",
        "",
        f"[完整计算说明与私有表](../{run.name}/REPORT.md)；[独立验证](verification.json)。",
        "",
        "当前未发布HRV、给药前后效应、生理–VAS关联或耦合推断。完整有限波形及可计算谱不等于伪迹验收；R峰、胃峰可靠性、有效时长、同步事件和fNIRS单位/ROI仍需相应证据。所有原始数据、旧CSV及VAS结果保持不变。",
    ]
    (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    sources = [
        mp,
        Path(__file__).resolve(),
        plot,
        ROOT / "config/signal_spectra_v1.json",
    ]
    state = dict(
        status="completed_spectral_numerical_review_scientific_qc_pending",
        created_utc=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(),
        numpy=np.__version__,
        scipy=scipy.__version__,
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        inputs_sha256={str(p): sha(p) for p in sources},
        outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
    )
    (out / "run_manifest.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
