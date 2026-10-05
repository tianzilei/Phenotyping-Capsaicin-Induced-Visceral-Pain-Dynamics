"""Independent checks and integrated descriptive delivery for D45."""

import collections
import csv
import json
import os
import platform
import statistics
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from audit_signal_readiness import ROOT, sha
from run_signal_spectra import write_rows
from path_resolver import resolve_input
from capsaicin.hash_baseline import check_reference
from review_signal_spectra import integrate_independent


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def describe(x):
    return dict(
        n=len(x),
        minimum=min(x) if x else None,
        median=statistics.median(x) if x else None,
        maximum=max(x) if x else None,
    )


def main():
    egg = ROOT / "08_outputs/egg_peak_diagnostics_20260918T103706Z_e4958b6c"
    cp = ROOT / "config/event_clock_review_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    clock = ROOT / cfg["source_run"]
    out = (
        ROOT
        / "08_outputs"
        / (
            "peak_clock_review_"
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
    for run in (egg, clock):
        manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
        if (
            not manifest["status"].startswith("completed")
            or "failures" in manifest["status"]
        ):
            raise ValueError("Incomplete source run")
        for field in (
            "inputs_sha256",
            "signals_sha256",
            "raw_sources_sha256",
            "outputs_sha256",
        ):
            for name, digest in manifest.get(field, {}).items():
                p = run / name if field == "outputs_sha256" else resolve_input(name)
                check_reference(run / "run_manifest.json", field, name, digest, p)
                verified += 1
    peaks = rows(egg / "peaks_private.csv")
    local = rows(egg / "local_peaks_private.csv")
    assert (
        len(peaks) == 4608
        and len({(r["path"], r["channel"], r["window_index"]) for r in peaks}) == 1536
    )
    error = max(
        abs(sum(float(r[k + "_fraction"]) for k in ("low", "middle", "high")) - 1)
        for r in peaks
    )
    assert error < 1e-12
    indexed = {
        (r["path"], r["channel"], r["window_index"], r["variant"]): r for r in peaks
    }
    assert len(indexed) == len(peaks)
    counts = collections.Counter(
        (r["path"], r["channel"], r["window_index"], r["variant"]) for r in local
    )
    assert all(counts[key] == int(r["local_peak_count"]) for key, r in indexed.items())
    for r in rows(egg / "variant_summary.csv"):
        g = [p for p in peaks if p["variant"] == r["variant"]]
        assert len(g) == int(r["channel_windows"])
        assert sum(p["boundary_maximum"] == "True" for p in g) == int(
            r["boundary_maxima"]
        )
        assert (
            abs(
                statistics.median(float(p["low_fraction"]) for p in g)
                - float(r["median_low_fraction"])
            )
            < 1e-12
        )
    prior = ROOT / "08_outputs/signal_spectra_20260918T102119Z_324f3d7b"
    source = [
        r
        for r in rows(prior / "windows_private.csv")
        if r["label"] == "EGG100C"
        and r["spectral_status"] == "computed_not_artifact_accepted"
    ]
    files = collections.defaultdict(list)
    for r in source:
        files[r["source_file_index"]].append(r)
    numeric_error = 0.0
    compared = 0
    for number, g in files.items():
        with np.load(
            prior / "spectra_private" / f"file_{int(number):04d}.npz"
        ) as arrays:
            for r in g:
                key = (r["path"], r["channel"], r["window_index"], "linear128")
                p = indexed[key]
                prefix = f"c{r['channel']}_w{r['window_index']}"
                f, power = arrays[prefix + "_f"], arrays[prefix + "_psd"]
                inside = np.flatnonzero((f >= 0.0083) & (f <= 0.15))
                winner = inside[np.argmax(power[inside])]
                assert float(p["maximum_hz"]) == f[winner]
                assert (p["boundary_maximum"] == "True") == (
                    winner in (inside[0], inside[-1])
                )
                count = sum(
                    power[i] > power[i - 1] and power[i] > power[i + 1]
                    for i in inside[1:-1]
                )
                assert int(p["local_peak_count"]) == count
                total = integrate_independent(f, power, 0.0083, 0.15)
                for name, lo, hi in [
                    ("low", 0.0083, 0.033),
                    ("middle", 0.033, 0.067),
                    ("high", 0.067, 0.15),
                ]:
                    difference = abs(
                        integrate_independent(f, power, lo, hi) / total
                        - float(p[name + "_fraction"])
                    )
                    assert difference < 1e-12
                    numeric_error = max(numeric_error, difference)
                    compared += 1
    edges = rows(
        ROOT
        / "02_quality_control/waveform_provenance_20260918T100523Z_0c21f681/digital_events_private.csv"
    )
    groups = collections.defaultdict(list)
    for r in edges:
        groups[(r["path"], r["channel"])].append(r)
    excursions = []
    for (path, channel), g in groups.items():
        for a, b in zip(g, g[1:]):
            before, after, next_before, next_after = map(
                float,
                (
                    a["previous_native"],
                    a["next_native"],
                    b["previous_native"],
                    b["next_native"],
                ),
            )
            start, stop = map(
                float,
                (a["time_from_recording_start_s"], b["time_from_recording_start_s"]),
            )
            assert stop > start
            if before == next_after and after == next_before and before != after:
                excursions.append(
                    dict(
                        path=path,
                        channel=channel,
                        polarity="positive" if after > before else "negative",
                        start_s=start,
                        stop_s=stop,
                        duration_s=stop - start,
                    )
                )
    write_rows(out / "digital_excursions_private.csv", excursions)
    dwell = {
        pol: describe([r["duration_s"] for r in excursions if r["polarity"] == pol])
        for pol in ("positive", "negative")
    }
    assert dwell["positive"]["n"] == len(rows(clock / "digital_pulses_private.csv"))
    protocols = rows(clock / "protocol_events_private.csv")
    pg = collections.defaultdict(list)
    for r in protocols:
        pg[r["path"]].append(r)
    gaps = []
    for path, g in pg.items():
        for a, b in zip(g, g[1:]):
            gaps.append(
                dict(
                    path=path,
                    previous_csv_row=a["csv_row"],
                    csv_row=b["csv_row"],
                    interval_label_seconds=float(b["start_label_seconds"])
                    - float(a["start_label_seconds"]),
                )
            )
    write_rows(out / "protocol_intervals_private.csv", gaps)
    protocol_intervals = describe([r["interval_label_seconds"] for r in gaps])
    protocol_files = rows(clock / "protocol_files_private.csv")
    empty_protocols = sum(int(r["parsed_records"]) == 0 for r in protocol_files)
    source_tests = (clock / "tests.log").read_text(encoding="utf-8")
    assert "Ran 105 tests" in source_tests and "\nOK\n" in source_tests
    plot = ROOT / "scripts/plot_peak_clock_review.R"
    with (out / "plot.log").open("w", encoding="utf-8") as f:
        subprocess.run(
            [
                "C:/Program Files/R/R-4.6.1/bin/Rscript.exe",
                str(plot),
                str(egg),
                str(out),
            ],
            cwd=ROOT,
            stdout=f,
            stderr=subprocess.STDOUT,
            env=dict(os.environ, TMP=str(out), TEMP=str(out)),
            check=True,
        )
    result = dict(
        status="passed",
        verified_hashes=verified,
        variant_channel_windows=len(peaks),
        fraction_sum_max_error=error,
        independently_recomputed_base_fractions=compared,
        max_fraction_difference=numeric_error,
        base_peak_and_local_count_checks=len(source),
        local_peak_rows=len(local),
        digital_excursions_seconds=dwell,
        protocol_intervals_label_seconds=protocol_intervals,
        protocol_files_without_events=empty_protocols,
        scientific_readiness=False,
    )
    (out / "verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    report = [
        "# 胃电峰诊断与事件时间核验",
        "",
        "## Material Passport",
        "",
        "- Origin Skill: academic-research-suite / experiment-agent",
        "- Origin Mode: run + validate",
        "- Verification: 工程与独立数值复核通过；生理推断条件未满足",
        "",
        "本轮完成522份原始记录的胃电敏感性诊断，以及241份评分日志、439份近红外协议（3077条事件）、26份有边沿的ACQ记录（788条边沿）的时间审计；未修改源数据、VAS编码或既有结果。记录和窗口数量不能解释为独立受试者数。",
        "",
        "## 胃电谱峰",
        "",
        "1536个通道窗口均完成三种规格，共4608次频谱描述。128秒线性去趋势规格有1106个边界最大值（72.0%）；256秒规格676个（44.0%）；整窗二次去趋势加128秒规格1105个（71.9%）。原128秒PSD重新计算与上一轮完全一致。",
        "",
        "256秒只有一个周期图段，原128秒有三个重叠段；分辨率变化也移动了频带内首个频点，边界比例下降不证明胃峰更可靠。二次去趋势基本未改变总体边界占比。合成红噪声和漂移也产生内部局部峰，因而不能把局部峰存在作为质控通过标准。没有选取最接近3 cpm的规格作为最终结果。",
        "",
        "![频谱规格与合成对照](peak_sensitivity.png)",
        "",
        "## 时间与触发",
        "",
        "241份日志含21种列结构，实际评分轮次数为0–20；现存脚本的15轮设置不能代表所有历史记录。3448个相邻已记录eval.started间隔中位59.9975秒、范围59.8669–60.3444秒。串口局部时间反复从接近零开始，不能直接与全局时间混算。",
        "",
        f"原生数字电平为0/5 V。{dwell['negative']['n']}个闭合负向变化的低电平时长中位{dwell['negative']['median']:.6f}秒、范围{dwell['negative']['minimum']:.6f}–{dwell['negative']['maximum']:.6f}秒；{dwell['positive']['n']}个闭合正向变化的高电平时长中位{dwell['positive']['median']:.6f}秒。前一审计中的‘正脉冲’只按上升后下降的数学定义；此处分别报告两种极性，没有认定高电平持续时间是触发脉宽。",
        "",
        "现存脚本生成于2025-07-12，名义输出1/0间隔0.1秒；这与当前数字通道的短下降形态不能直接等同。数字边沿可能分别响应串口命令，也可能涉及设备转换；本次没有证明该机制，不能据此设定触发极性或将第一条边沿指定为给药。",
        "",
        f"439份近红外协议的声明行数与解析行数全部一致，其中{empty_protocols}份没有事件行。全部3077条Pre.Rest/Task/Pos.Rest原值为45/45/0；相邻列出的Start Time标签共{protocol_intervals['n']}个间隔，中位{protocol_intervals['median']}秒、范围{protocol_intervals['minimum']}–{protocol_intervals['maximum']}秒。这些标签和任务设置未验证为实际给药或采集同步记录。",
        "",
        "## 复核与后续边界",
        "",
        f"105项合成测试通过；{verified}项输入、代码及输出哈希通过。独立重算1536个原规格最大值和局部峰数量、4608个分频带比例，最大比例误差{numeric_error:.3g}；全部规格的低/中/高频比例和与1的最大偏差{error:.3g}。图表及明细单独保存。",
        "",
        "连续VAS分析结果继续有效于既有探索范围。给药前后生理比较、VAS关联和跨模态耦合仍需逐记录事件语义与时钟映射、伪迹验收，以及fNIRS单位/通道ROI依据；状态转移仍待有依据的VAS阈值。上述条件尚不能由规律间隔、文件名或有限数值替代。",
        "",
        f"[胃电完整诊断](../{egg.name}/REPORT.md) · [事件完整审计](../../02_quality_control/{clock.name}/REPORT.md) · [既有VAS交付](../analysis_delivery_20260917T160429Z_4ce9a192/REPORT.md)",
    ]
    (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    inputs = [
        cp,
        Path(__file__).resolve(),
        plot,
        ROOT / "scripts/review_signal_spectra.py",
        ROOT / "scripts/audit_signal_readiness.py",
        ROOT / "scripts/run_signal_spectra.py",
        egg / "run_manifest.json",
        clock / "run_manifest.json",
        prior / "run_manifest.json",
        ROOT
        / "02_quality_control/waveform_provenance_20260918T100523Z_0c21f681/digital_events_private.csv",
    ]
    manifest = dict(
        status="completed_verified_descriptions",
        created_utc=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(),
        numpy=np.__version__,
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        inputs_sha256={str(p): sha(p) for p in inputs},
        outputs_sha256={
            str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()
        },
    )
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
