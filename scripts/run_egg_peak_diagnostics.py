"""Frozen EGG peak diagnostics with synthetic controls and no clinical inference."""

import collections
import csv
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import scipy
import bioread
from scipy import signal
from audit_signal_readiness import ROOT, sha
from run_signal_spectra import write_rows
from capsaicin.data_locations import resolve_input, relocation_evidence
from capsaicin.hash_baseline import check_reference

sys.path.insert(0, str(ROOT / "src"))
from capsaicin.egg_peaks import variant_spectrum
from capsaicin.signal_spectra import resample_exact


def main():
    cp = ROOT / "config/egg_peak_diagnostics_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    sc = ROOT / cfg["source_config"]
    base = json.loads(sc.read_text(encoding="utf-8"))
    prior = ROOT / cfg["source_run"]
    pm = prior / "run_manifest.json"
    old = json.loads(pm.read_text(encoding="utf-8"))
    out = (
        ROOT
        / "08_outputs"
        / (
            "egg_peak_diagnostics_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    tmp = out / "test_temp"
    tmp.mkdir()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "peaks_private.csv")],
        cwd=ROOT,
        check=True,
    )
    sources = [
        cp,
        sc,
        pm,
        Path(__file__).resolve(),
        ROOT / "scripts/run_signal_spectra.py",
        ROOT / "scripts/audit_signal_readiness.py",
        ROOT / "src/capsaicin/egg_peaks.py",
        ROOT / "src/capsaicin/signal_spectra.py",
        ROOT / "tests/test_egg_peaks.py",
        prior / "windows_private.csv",
    ]
    for field in ["inputs_sha256", "outputs_sha256"]:
        for name, digest in old[field].items():
            check_reference(
                pm,
                field,
                name,
                digest,
                prior / name if field == "outputs_sha256" else resolve_input(name),
            )
    sources += relocation_evidence()
    state = dict(
        status="running",
        created_utc=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(),
        numpy=np.__version__,
        scipy=scipy.__version__,
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        inputs_sha256={str(p): sha(p) for p in sources},
        signals_sha256={},
    )
    rows = []
    local = []
    controls = []
    failures = []
    started = time.monotonic()
    max_prior_psd_error = 0.0
    print(out, flush=True)

    def save():
        write_rows(out / "peaks_private.csv", rows)
        write_rows(out / "local_peaks_private.csv", local)
        write_rows(out / "synthetic_controls.csv", controls)
        write_rows(out / "failures_private.csv", failures)
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    try:
        with (out / "tests.log").open("w", encoding="utf-8") as f:
            subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=ROOT,
                stdout=f,
                stderr=subprocess.STDOUT,
                env=dict(os.environ, TMP=str(tmp), TEMP=str(tmp)),
                check=True,
            )
        rng = np.random.default_rng(cfg["synthetic_seed"])
        t = np.arange(1120) / 4
        u = (t - t.mean()) / 140
        for case in cfg["synthetic_cases"]:
            for rep in range(cfg["synthetic_replicates_per_case"]):
                sine = np.sin(2 * np.pi * 0.05 * t + rng.uniform(0, 2 * np.pi))
                noise = 0.15 * rng.normal(size=len(t))
                if case == "sine":
                    y = sine + noise
                elif case == "quadratic_drift":
                    y = 8 * u**2 + noise
                elif case == "sine_plus_drift":
                    y = sine + 8 * u**2 + noise
                elif case == "red_noise":
                    y = signal.lfilter([1], [1, -0.99], rng.normal(size=len(t)))
                else:
                    y = 4 * (t >= 140) + noise
                for variant in cfg["variants"]:
                    r, _, _ = variant_spectrum(y, 4, variant)
                    r.update(case=case, replicate=rep)
                    controls.append(r)
                    if (
                        case == "sine"
                        and abs(r["maximum_hz"] - 0.05) > 1 / variant["segment_seconds"]
                    ):
                        raise AssertionError("Synthetic sine peak not recovered")
        groups = collections.defaultdict(list)
        for r in csv.DictReader((prior / "windows_private.csv").open(encoding="utf-8")):
            if (
                r["label"] == "EGG100C"
                and r["spectral_status"] == "computed_not_artifact_accepted"
            ):
                groups[r["path"]].append(r)
        for number, (name, group) in enumerate(sorted(groups.items()), 1):
            if time.monotonic() - started > cfg["timeout_seconds"]:
                raise TimeoutError("Partial analysis retained")
            try:
                p = resolve_input(name)
                digest = sha(p)
                if digest != old["signals_sha256"][name]:
                    raise ValueError("Raw input changed")
                state["signals_sha256"][name] = digest
                with p.open("rb") as f:
                    reader = bioread.reader.Reader(f)
                    reader._read_headers()
                    reader._read_data(None, bioread.reader.CHUNK_SIZE)
                    data = reader.datafile
                file_rows = []
                file_local = []
                for item in group:
                    k = int(item["channel"])
                    w = int(item["window_index"])
                    c = data.channels[k]
                    if (
                        c.name != "EGG100C"
                        or c.samples_per_second != 2000
                        or c.units != "mV"
                    ):
                        raise ValueError("Metadata changed")
                    raw = c.data[w * 600000 : (w + 1) * 600000]
                    y = resample_exact(resample_exact(raw, 2000, 100), 100, 4)[40:-40]
                    for variant in cfg["variants"]:
                        r, peaks, (f, power) = variant_spectrum(y, 4, variant)
                        if variant["name"] == "linear128":
                            with np.load(
                                prior
                                / "spectra_private"
                                / f"file_{int(item['source_file_index']):04d}.npz"
                            ) as arrays:
                                old_power = arrays[f"c{k}_w{w}_psd"]
                                np.testing.assert_allclose(
                                    power, old_power, rtol=1e-12, atol=1e-15
                                )
                                max_prior_psd_error = max(
                                    max_prior_psd_error,
                                    float(np.max(np.abs(power - old_power))),
                                )
                        r.update(
                            path=name,
                            channel=k,
                            window_index=w,
                            stage=item["stage"],
                            prior_boundary=item["band_max_boundary"],
                            raw_constant_span_s=item["longest_constant_span_s"],
                        )
                        file_rows.append(r)
                        file_local.extend(
                            dict(
                                path=name,
                                channel=k,
                                window_index=w,
                                variant=variant["name"],
                                **peak,
                            )
                            for peak in peaks
                        )
                rows.extend(file_rows)
                local.extend(file_local)
            except Exception as exc:
                failures.append(dict(path=name, error=f"{type(exc).__name__}: {exc}"))
            if number % 40 == 0 or number == len(groups):
                save()
                print(
                    f"{number}/{len(groups)} records; variant windows={len(rows)}; failures={len(failures)}",
                    flush=True,
                )
        summary = []
        for variant in cfg["variants"]:
            group = [r for r in rows if r["variant"] == variant["name"]]
            summary.append(
                dict(
                    variant=variant["name"],
                    channel_windows=len(group),
                    boundary_maxima=sum(r["boundary_maximum"] for r in group),
                    with_interior_local_peak=sum(
                        r["local_peak_count"] > 0 for r in group
                    ),
                    median_low_fraction=float(
                        np.median([r["low_fraction"] for r in group])
                    ),
                    median_middle_fraction=float(
                        np.median([r["middle_fraction"] for r in group])
                    ),
                    median_maximum_cpm=float(
                        np.median([r["maximum_hz"] * 60 for r in group])
                    ),
                )
            )
        sensitivity = []
        pairs = collections.defaultdict(dict)
        for r in rows:
            pairs[(r["path"], r["channel"], r["window_index"])][r["variant"]] = r
        for variant in cfg["variants"][1:]:
            matched = [(g["linear128"], g[variant["name"]]) for g in pairs.values()]
            sensitivity.append(
                dict(
                    variant=variant["name"],
                    paired_channel_windows=len(matched),
                    base_boundary_to_interior=sum(
                        a["boundary_maximum"] and not b["boundary_maximum"]
                        for a, b in matched
                    ),
                    peak_within_one_original_bin=sum(
                        abs(a["maximum_hz"] - b["maximum_hz"])
                        <= cfg["matching_tolerance_hz"]
                        for a, b in matched
                    ),
                    median_abs_difference_cpm=float(
                        np.median(
                            [
                                abs(a["maximum_hz"] - b["maximum_hz"]) * 60
                                for a, b in matched
                            ]
                        )
                    ),
                )
            )
        channel_pairs = collections.defaultdict(list)
        for r in rows:
            if r["variant"] == "linear128":
                channel_pairs[(r["path"], r["window_index"])].append(r)
        pair_rows = []
        for (name, w), g in channel_pairs.items():
            if len(g) != 2:
                continue
            a, b = sorted(g, key=lambda r: r["channel"])
            pair_rows.append(
                dict(
                    path=name,
                    window_index=w,
                    both_boundary=a["boundary_maximum"] and b["boundary_maximum"],
                    peak_difference_cpm=abs(a["maximum_hz"] - b["maximum_hz"]) * 60,
                    both_have_local_peak=a["local_peak_count"] > 0
                    and b["local_peak_count"] > 0,
                )
            )
        write_rows(out / "channel_pairs_private.csv", pair_rows)
        write_rows(out / "variant_summary.csv", summary)
        write_rows(out / "sensitivity_summary.csv", sensitivity)
        synth = []
        for case in cfg["synthetic_cases"]:
            for variant in cfg["variants"]:
                g = [
                    r
                    for r in controls
                    if r["case"] == case and r["variant"] == variant["name"]
                ]
                synth.append(
                    dict(
                        case=case,
                        variant=variant["name"],
                        replicates=len(g),
                        boundary_maxima=sum(r["boundary_maximum"] for r in g),
                        with_local_peak=sum(r["local_peak_count"] > 0 for r in g),
                    )
                )
        write_rows(out / "synthetic_summary.csv", synth)
        overall = dict(
            files=len(groups),
            files_failed=len(failures),
            base_channel_windows=len(pairs),
            variant_rows=len(rows),
            max_prior_psd_error=max_prior_psd_error,
            paired_recording_windows=len(pair_rows),
            both_channels_boundary=sum(r["both_boundary"] for r in pair_rows),
            synthetic_fits=len(controls),
        )
        (out / "summary.json").write_text(
            json.dumps(overall, indent=2), encoding="utf-8"
        )
        report = [
            "# 胃电低频边界峰诊断",
            "",
            "## Material Passport",
            "",
            "- Origin Skill: academic-research-suite / experiment-agent",
            "- Origin Mode: run + validate",
            "- Verification: 工程与数值一致性已检查；胃节律未验收",
            "",
            json.dumps(overall, ensure_ascii=False, indent=2),
            "",
            "|规格|通道窗|边界最大值|含内部局部峰|低频功率比例中位|中频功率比例中位|",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for r in summary:
            report.append(
                f"|{r['variant']}|{r['channel_windows']}|{r['boundary_maxima']}|{r['with_interior_local_peak']}|{r['median_low_fraction']:.4f}|{r['median_middle_fraction']:.4f}|"
            )
        report += [
            "",
            "低/中/高频分界为0.0083、0.033、0.067、0.15 Hz；内部局部峰仅是严格高于相邻频点的数学极值，所有局部峰均保存。没有把它解释为可靠胃峰，也没有据峰值选择最佳通道。",
            "",
            "|与原128秒比较|配对窗|原边界转为内部最大值|峰差不超过原1频点|峰差绝对值中位(cpm)|",
            "|---|---:|---:|---:|---:|",
        ]
        for r in sensitivity:
            report.append(
                f"|{r['variant']}|{r['paired_channel_windows']}|{r['base_boundary_to_interior']}|{r['peak_within_one_original_bin']}|{r['median_abs_difference_cpm']:.4f}|"
            )
        report += [
            "",
            "256秒分段只有1个周期图段（原128秒有3个重叠段），分辨率提高同时增加方差，不能直接当作改进。二次去趋势可能删掉真实慢成分；这里只诊断规格敏感性，不替换原分析。",
            "",
            "合成压力对照（每类20份，未用于确定临床阈值）：",
            "",
            "|合成情景|规格|边界最大值|含内部局部峰|",
            "|---|---|---:|---:|",
        ]
        for r in synth:
            report.append(
                f"|{r['case']}|{r['variant']}|{r['boundary_maxima']}/{r['replicates']}|{r['with_local_peak']}/{r['replicates']}|"
            )
        report += [
            "",
            "含内部峰也可能是噪声或阶跃泄漏，不能单凭局部峰存在通过QC。低频边界可与漂移、真实慢变化或分辨率不足有关，本轮不能唯一确定原因。",
            "",
            f"两通道配对{len(pair_rows)}个记录窗，其中{overall['both_channels_boundary']}个两通道均为边界最大值；共同低频不能被解释为独立胃来源或跨器官耦合。",
            "",
            "本轮全部时间为记录相对窗口，未对齐给药。无受试者推断、无p值、无临床频率阈值。源信号、旧CSV及VAS结果不改；101项合成测试通过，原128秒PSD重新计算与D44一致，完整输入和代码摘要随运行保存。",
        ]
        (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        state["status"] = (
            "completed_diagnostic_descriptions"
            if not failures
            else "completed_with_failures"
        )
    except Exception as exc:
        state.update(status="failed", error=str(exc))
        raise
    finally:
        save()
        state["outputs_sha256"] = {
            str(p.relative_to(out)): sha(p)
            for p in out.rglob("*")
            if p.is_file() and p.name != "run_manifest.json"
        }
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )
    print(json.dumps(overall), flush=True)


if __name__ == "__main__":
    main()
