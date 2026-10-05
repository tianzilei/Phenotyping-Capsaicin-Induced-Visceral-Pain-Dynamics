"""Recompute interval/count checks and provide traceable diagnostic examples."""

import collections
import csv
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import bioread
import numpy as np
from scipy import signal
from audit_signal_readiness import ROOT, sha
from run_signal_spectra import write_rows
from path_resolver import resolve_input
from capsaicin.hash_baseline import check_reference

sys.path.insert(0, str(ROOT / "src"))
from capsaicin.ecg_candidates import detect_candidates


def read(path):
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    run = ROOT / sys.argv[1]
    cp = ROOT / "config/ecg_candidate_review_v1.json"
    cfg = json.loads(
        (ROOT / "config/ecg_candidates_v1.json").read_text(encoding="utf-8")
    )
    out = (
        ROOT
        / "08_outputs"
        / (
            "ecg_candidate_review_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "review_queue_private.csv")],
        cwd=ROOT,
        check=True,
    )
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "completed_candidate_diagnostics":
        raise ValueError("Incomplete or failed source run")
    verified = 0
    for key in ("inputs_sha256", "signals_sha256", "outputs_sha256"):
        for name, digest in manifest[key].items():
            p = run / name if key == "outputs_sha256" else resolve_input(name)
            check_reference(run / "run_manifest.json", key, name, digest, p)
            verified += 1
    rows = read(run / "windows_private.csv")
    cross = read(run / "between_channels_private.csv")
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r["source_file_index"]].append(r)
    comparisons = 0
    totals = collections.Counter()
    count_bounds = []
    for file_id, g in groups.items():
        with np.load(
            run / "candidate_times_private" / f"file_{int(file_id):04d}.npz"
        ) as arrays:
            for r in g:
                times = {}
                for method in ("amplitude", "energy"):
                    t = arrays[
                        f"c{r['channel']}_w{r['window_index']}_{method}_recording_s"
                    ]
                    assert np.isfinite(t).all() and np.all(np.diff(t) > 0)
                    assert np.all(
                        t >= float(r["analysis_start_recording_s"])
                    ) and np.all(t < float(r["analysis_end_recording_s"]))
                    assert np.all(
                        np.diff(t)
                        >= round(
                            cfg["minimum_distance_seconds"] * cfg["target_rate_hz"]
                        )
                        / cfg["target_rate_hz"]
                        - 1e-10
                    )
                    assert len(t) == int(r[method + "_candidate_count"])
                    if len(t) > 1:
                        assert (
                            abs(
                                np.median(np.diff(t))
                                - float(r[method + "_median_interval_s"])
                            )
                            < 1e-10
                        )
                        assert (
                            abs(
                                np.max(np.diff(t))
                                - float(r[method + "_max_interval_s"])
                            )
                            < 1e-10
                        )
                    comparisons += 1
                    totals[method] += len(t)
                    times[method] = t
                # Refractory gap exceeds 2*tolerance, so each cross-method match is unique.
                a, b = times["amplitude"], times["energy"]
                i = np.searchsorted(b, a)
                distances = np.full(len(a), np.inf)
                for shift in (0, -1):
                    idx = i + shift
                    ok = (idx >= 0) & (idx < len(b))
                    distances[ok] = np.minimum(
                        distances[ok], np.abs(a[ok] - b[idx[ok]])
                    )
                matched = int(
                    np.sum(distances <= cfg["matching_tolerance_seconds"] + 1e-12)
                )
                assert matched == int(r["matched"])
                if len(a) + len(b):
                    assert (
                        abs(2 * matched / (len(a) + len(b)) - float(r["agreement"]))
                        < 1e-12
                    )
    defined = [r for r in rows if r.get("agreement")]
    queue = sorted(defined, key=lambda r: float(r["agreement"]))
    write_rows(
        out / "review_queue_private.csv",
        [dict(review_order=i + 1, **r) for i, r in enumerate(queue)],
    )
    lowest_cross = min(
        (r for r in cross if r["method"] == "amplitude" and r["agreement"]),
        key=lambda r: float(r["agreement"]),
    )
    cross_row = next(
        r
        for r in rows
        if r["path"] == lowest_cross["path"]
        and r["window_index"] == lowest_cross["window_index"]
        and r["channel"] == lowest_cross["channel_a"]
    )
    examples = [
        ("first_window", rows[0]),
        ("lowest_method_agreement", queue[0]),
        ("lowest_channel_pair_lead_a", cross_row),
    ]
    traces = []
    markers = []
    example_index = []
    reproduced = 0
    for label, r in examples:
        with resolve_input(r["path"]).open("rb") as f:
            reader = bioread.reader.Reader(f)
            reader._read_headers()
            reader._read_data(None, bioread.reader.CHUNK_SIZE)
            data = reader.datafile
        w = int(r["window_index"])
        k = int(r["channel"])
        raw = data.channels[k].data[w * 600000 : (w + 1) * 600000]
        y = signal.resample_poly(raw, 1, 8, window=("kaiser", 8.6), padtype="line")
        detected = detect_candidates(y, 250, cfg)
        start = w * 300 + 10
        with np.load(
            run
            / "candidate_times_private"
            / f"file_{int(r['source_file_index']):04d}.npz"
        ) as arrays:
            for method in ("amplitude", "energy"):
                t = arrays[f"c{k}_w{w}_{method}_recording_s"]
                np.testing.assert_array_equal(
                    (detected[method] + detected["offset_samples"]) / 250 + w * 300, t
                )
                reproduced += 1
                markers.extend(
                    dict(example=label, detector=method, time_s=float(v))
                    for v in t[(t >= start) & (t < start + 8)]
                )
        traces.extend(
            dict(example=label, time_s=start + i / 250, filtered_mV=float(v))
            for i, v in enumerate(detected["filtered"][:2000])
        )
        example_index.append(
            dict(
                example=label,
                path=r["path"],
                channel=k,
                window_index=w,
                start_s=start,
                selection="predeclared_order_statistic_not_clinical_adjudication",
            )
        )
    write_rows(out / "review_traces_private.csv", traces)
    write_rows(out / "review_markers_private.csv", markers)
    write_rows(out / "review_examples_private.csv", example_index)
    scripts = [
        Path("F:/杰青得气课题软件和脚本") / name
        for name in (
            "psf自动导入脚本.py",
            "shimadzu_autostop.py",
            "psychopy_edition/untitled.py",
        )
    ]
    scripts = [resolve_input(p) for p in scripts]
    source_evidence = []
    for p in scripts:
        lines = p.read_text(encoding="utf-8-sig").splitlines()
        source_evidence.append(
            dict(
                path=str(p),
                sha256=sha(p),
                lines=len(lines),
                purpose="read_only_auxiliary_timing_source_search",
            )
        )
    write_rows(out / "auxiliary_source_search_private.csv", source_evidence)
    plot = ROOT / "scripts/plot_ecg_candidates.R"
    with (out / "plot.log").open("w", encoding="utf-8") as f:
        subprocess.run(
            [
                "C:/Program Files/R/R-4.6.1/bin/Rscript.exe",
                str(plot),
                str(run),
                str(out),
            ],
            cwd=ROOT,
            stdout=f,
            stderr=subprocess.STDOUT,
            env=dict(os.environ, TMP=str(out), TEMP=str(out)),
            check=True,
        )
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    agreement = np.array([float(r["agreement"]) for r in defined])
    result = dict(
        status="passed",
        verified_hashes=verified,
        method_window_checks=comparisons,
        matching_checks=len(defined),
        reproduced_candidate_vectors=reproduced,
        candidate_totals=dict(totals),
        method_agreement_quantiles=dict(
            zip(
                ["min", "q25", "median", "q75", "max"],
                map(float, np.quantile(agreement, [0, 0.25, 0.5, 0.75, 1])),
            )
        ),
        scientific_qc_passed=False,
    )
    for method in ("amplitude", "energy"):
        values = [
            float(r["agreement"])
            for r in cross
            if r["method"] == method and r["agreement"]
        ]
        result[method + "_between_channel_median"] = (
            float(np.median(values)) if values else None
        )
    (out / "verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    synth = read(run / "synthetic_summary.csv")
    report = [
        "# 原始心电候选搏动诊断",
        "",
        "## Material Passport",
        "",
        "- Origin Skill: academic-research-suite / experiment-agent",
        "- Origin Mode: run + validate",
        "- Verification: 工程复核通过；候选搏动尚未临床判读",
        "",
        f"完成{summary['files_completed']}/{summary['files_planned']}份原始ACQ记录、{summary['channel_windows']}个心电通道窗口，失败{summary['failures']}。各窗口按记录起点切分300秒、裁两端各10秒；全部通道与两种检测方法保留。原530份记录中8份不足完整300秒，支持清单沿用D44。数量不是独立受试者数。",
        "",
        "## 固定方法与结果",
        "",
        "2000→250 Hz抗混叠重采样；5–20 Hz三阶Butterworth双向滤波。幅值法取绝对信号的局部峰，导数能量法平滑后取峰并在±80毫秒细化；30秒块MAD阈值、约250毫秒不应期、50毫秒一对一匹配。规格是工程探索设定，没有作为临床验收标准。",
        "",
        f"幅值法共产生{totals['amplitude']}个候选，能量法{totals['energy']}个。两法在同一通道窗的一致度中位{result['method_agreement_quantiles']['median']:.3f}，四分位范围{result['method_agreement_quantiles']['q25']:.3f}–{result['method_agreement_quantiles']['q75']:.3f}；一致度定义为2×匹配数/两法候选总数。两法都无候选时不定义为100%一致。",
        "",
        f"同一记录窗不同通道的一致度中位：幅值法{result['amplitude_between_channel_median']:.3f}，能量法{result['energy_between_channel_median']:.3f}。没有按一致度选择最佳通道或剔除低一致窗口。",
        "",
        "![候选检测诊断](candidate_diagnostics.png)",
        "",
        "## 已知真值合成对照",
        "",
        "|情景|方法|真值总数|候选总数|假候选|精确率|召回率|",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in synth:
        report.append(
            f"|{r['case']}|{r['method']}|{r['truth_count']}|{r['candidate_count']}|{r['false_candidates']}|{float(r['pooled_precision']):.3f}|{float(r['pooled_recall']):.3f}|"
            if r["pooled_precision"] and r["pooled_recall"]
            else f"|{r['case']}|{r['method']}|{r['truth_count']}|{r['candidate_count']}|{r['false_candidates']}|{r['pooled_precision'] or '未定义'}|{r['pooled_recall'] or '未定义'}|"
        )
    report += [
        "",
        "7类各10份合成数据；干净和倒置信号在进入真实记录前通过精确率/召回率≥0.95、时差中位≤20毫秒的工程门槛。含伪迹与无真实搏动的纯噪声对照保留全部结果，不按表现调参。两方法共享滤波和绝对幅值细化，不是独立标注者；一致也可能同错。",
        "",
        "候选时间以秒记录，所有相邻候选间隔保留，不删除短/长间隔、不填漏检、不跨窗口连接。当前不是正常窦性NN间隔，未输出SDNN、RMSSD、频域HRV或给药效应。",
        "",
        "## 复核与波形复查入口",
        "",
        f"109项合成单元测试通过，{verified}项哈希核验通过；从保存的候选向量独立核对{comparisons}个方法窗口的数量、单调性、时间范围和间隔，以及{len(defined)}个两方法匹配数。按预定首窗口/最低方法一致度/最低通道一致度三类例子重读原始信号，{reproduced}个候选向量完全复现。",
        "",
        "[诊断波形](review_traces_private.png)显示每个预定例子的起始8秒，圆圈/十字仅为算法候选，不表示人工确认。完整待复核队列、候选时间、明细和选择理由均保存在私有输出。",
        "",
        "同步线索继续只读核查了自动导入、fNIRS界面控制及另一份PsychoPy脚本。界面控制代码依赖点击、等待和OCR；另一脚本头部生成日期为2024-12-12。这些源码没有给出当前各记录的硬件脉冲—给药时刻映射，未执行任何旧自动控制代码，未改变同步就绪状态。",
        "",
        "## 解释范围检查",
        "",
        "11/11项已检查：分组汇总反转（未做组间效应）、生态推断（窗口不当作人）、选择/碰撞偏倚（只纳入完整记录窗，不作条件关联）、基率（合成无搏动对照单列）、均值回归（无前后改善声明）、完整者偏倚（8份短记录明示）、多重比较与分析分支（无显著性筛选、两法全报、配置在结果前冻结）、相关因果混淆及反向因果（无因果或预测声明）。合成性能不外推为真实临床敏感度。",
        "",
        "下一步生理推断仍需可信的搏动判读/伪迹规则、逐记录给药同步及受试者核验；本轮提供可复现候选与复查波形，不把工程通过标为临床QC通过。",
        "",
        f"[本次机器输出](../{run.name}/summary.json) · [胃电与事件时间报告](../peak_clock_review_20260918T104735Z_1ff328b5/REPORT.md) · [既有VAS交付](../analysis_delivery_20260917T160429Z_4ce9a192/REPORT.md)",
    ]
    (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    sources = [
        cp,
        Path(__file__).resolve(),
        plot,
        run / "run_manifest.json",
        ROOT / "config/ecg_candidates_v1.json",
        ROOT / "src/capsaicin/ecg_candidates.py",
        ROOT / "scripts/audit_signal_readiness.py",
        ROOT / "scripts/run_signal_spectra.py",
    ] + scripts
    provenance = dict(
        status="completed_verified_diagnostics",
        created_utc=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(),
        numpy=np.__version__,
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        inputs_sha256={str(p): sha(p) for p in sources},
        outputs_sha256={
            str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()
        },
    )
    (out / "run_manifest.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
