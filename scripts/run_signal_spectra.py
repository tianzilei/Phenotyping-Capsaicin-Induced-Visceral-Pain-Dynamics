"""Execute frozen recording-relative spectral descriptions of all raw analog channels."""

import collections
import csv
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import bioread
import numpy as np
import scipy
from audit_signal_readiness import ROOT, sha
from path_resolver import resolve_external_path, execution_config, relocation_evidence

sys.path.insert(0, str(ROOT / "src"))
from capsaicin.signal_spectra import window_spectrum
from capsaicin.waveform_audit import describe


def write_rows(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    cp = execution_config(ROOT / "config/signal_spectra_v2.json")
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    prev = ROOT / cfg["source_run"] / "run_manifest.json"
    previous = json.loads(prev.read_text(encoding="utf-8"))
    mapping = ROOT / cfg["mapping"]
    links = list(csv.DictReader(mapping.open(encoding="utf-8-sig")))
    assert all(r["stage"] in cfg["allowed_stages"] for r in links)
    paths = sorted(
        {
            r["path"]
            for r in links
            if Path(r["path"]).suffix.lower() == ".acq"
            and not Path(r["path"]).name.startswith("._")
        }
    )
    stages = {
        name: sorted({r["stage"] for r in links if r["path"] == name}) for name in paths
    }
    out = (
        ROOT
        / "08_outputs"
        / (
            "signal_spectra_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    spectra = out / "spectra_private"
    spectra.mkdir()
    temp = out / "test_temp"
    temp.mkdir()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "windows_private.csv")],
        cwd=ROOT,
        check=True,
    )
    sources = [
        cp,
        prev,
        mapping,
        Path(__file__).resolve(),
        ROOT / "scripts/audit_signal_readiness.py",
        ROOT / "src/capsaicin/signal_spectra.py",
        ROOT / "src/capsaicin/waveform_audit.py",
        ROOT / "tests/test_signal_spectra.py",
    ]
    # Include numerical implementation hashes in addition to package version/environment.
    sources += relocation_evidence() + [ROOT / "scripts/path_resolver.py"]
    sources += [
        Path(scipy.signal.resample_poly.__code__.co_filename),
        Path(scipy.signal.welch.__code__.co_filename),
    ]
    state = dict(
        status="running",
        created_utc=datetime.now(timezone.utc).isoformat(),
        config_version=cfg["version"],
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
    support = []
    failures = []
    began = time.monotonic()
    print(out, flush=True)

    def save():
        write_rows(out / "windows_private.csv", rows)
        write_rows(out / "support_private.csv", support)
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
                env=dict(os.environ, TMP=str(temp), TEMP=str(temp)),
                check=True,
            )
        for number, name in enumerate(paths, 1):
            if time.monotonic() - began > cfg["timeout_seconds"]:
                raise TimeoutError("Frozen analysis timeout; partial results retained")
            p = resolve_external_path(name)
            file_rows = []
            file_support = []
            saved = {}
            try:
                if p is None:
                    raise FileNotFoundError(f"unresolved external path: {name}")
                digest = sha(p)
                if digest != previous["signals_sha256"][name]:
                    raise ValueError("Input changed since whole-waveform audit")
                state["signals_sha256"][name] = digest
                with p.open("rb") as f:
                    reader = bioread.reader.Reader(f)
                    reader._read_headers()
                    reader._read_data(None, bioread.reader.CHUNK_SIZE)
                    data = reader.datafile
                for k, c in enumerate(data.channels):
                    if c.name not in ["ECG100C", "EGG100C"]:
                        continue
                    if c.samples_per_second != cfg["input_rate_hz"] or c.units != "mV":
                        raise ValueError("Unexpected raw channel rate or unit")
                    x = np.asarray(c.data)
                    if len(x) != c.point_count:
                        raise ValueError("Truncated channel")
                    nwin = int(cfg["input_rate_hz"] * cfg["window_seconds"])
                    full = len(x) // nwin
                    file_support.append(
                        dict(
                            path=name,
                            stage=";".join(stages[name]),
                            channel=k,
                            label=c.name,
                            rate_hz=c.samples_per_second,
                            units=c.units,
                            n_samples=len(x),
                            complete_windows=full,
                            unused_tail_seconds=(len(x) % nwin) / c.samples_per_second,
                        )
                    )
                    for w in range(full):
                        raw = x[w * nwin : (w + 1) * nwin]
                        description = describe(raw, c.samples_per_second)
                        result, psd = window_spectrum(raw, c.name, cfg)
                        r = dict(
                            path=name,
                            stage=";".join(stages[name]),
                            channel=k,
                            label=c.name,
                            units="mV",
                            window_index=w,
                            start_recording_s=w * cfg["window_seconds"],
                            end_recording_s=(w + 1) * cfg["window_seconds"],
                            analysis_start_recording_s=w * cfg["window_seconds"]
                            + cfg["edge_trim_seconds_each_side"],
                            analysis_end_recording_s=(w + 1) * cfg["window_seconds"]
                            - cfg["edge_trim_seconds_each_side"],
                            source_file_index=number,
                        )
                        r.update(description)
                        r.update(result)
                        file_rows.append(r)
                        if psd is not None:
                            saved[f"c{k}_w{w}_f"] = psd[0]
                            saved[f"c{k}_w{w}_psd"] = psd[1]
                np.savez_compressed(spectra / f"file_{number:04d}.npz", **saved)
                rows.extend(file_rows)
                support.extend(file_support)
            except Exception as exc:
                failures.append(dict(path=name, error=f"{type(exc).__name__}: {exc}"))
            if number % 25 == 0 or number == len(paths):
                save()
                print(
                    f"{number}/{len(paths)} records; windows={len(rows)}; failures={len(failures)}",
                    flush=True,
                )
        # Recording-level summaries for visualization only; no clinical group comparisons.
        record_rows = []
        groups = collections.defaultdict(list)
        for r in rows:
            if r["spectral_status"] == "computed_not_artifact_accepted":
                groups[(r["path"], r["label"])].append(r)
        for (name, label), g in groups.items():
            r = dict(
                path=name,
                label=label,
                stage=";".join(stages[name]),
                channel_windows=len(g),
                channels=len({x["channel"] for x in g}),
                complete_time_windows=len({x["window_index"] for x in g}),
            )
            if label == "EGG100C":
                r.update(
                    median_norm_fraction=float(
                        np.median([x["norm_fraction"] for x in g])
                    ),
                    median_band_max_cpm=float(
                        np.median([x["band_max_cpm"] for x in g])
                    ),
                    median_abs_peak_difference_cpm=float(
                        np.median(
                            [
                                abs(x["band_max_hz"] - x["band_max_hz_64s"]) * 60
                                for x in g
                            ]
                        )
                    ),
                    boundary_peak_fraction=float(
                        np.mean([x["band_max_boundary"] for x in g])
                    ),
                )
            else:
                r.update(
                    median_ecg_band_power_native2=float(
                        np.median([x["ecg_band_power_native2"] for x in g])
                    ),
                    median_line_band_power_native2=float(
                        np.median([x["line_band_power_native2"] for x in g])
                    ),
                )
            record_rows.append(r)
        write_rows(out / "recording_summaries_private.csv", record_rows)
        egg = [
            r
            for r in rows
            if r["label"] == "EGG100C"
            and r["spectral_status"] == "computed_not_artifact_accepted"
        ]
        summary = dict(
            files_planned=len(paths),
            files_completed=len({r["path"] for r in support}),
            file_failures=len(failures),
            analog_channels=len(support),
            files_with_complete_windows=len({r["path"] for r in rows}),
            complete_recording_windows=len(
                {(r["path"], r["window_index"]) for r in rows}
            ),
            channel_windows=len(rows),
            windows_by_label=dict(collections.Counter(r["label"] for r in rows)),
            status=dict(collections.Counter(r["spectral_status"] for r in rows)),
            raw_constant_span_ge1s_by_label=dict(
                collections.Counter(
                    r["label"] for r in rows if r["longest_constant_span_s"] >= 1
                )
            ),
            egg_computed_windows=len(egg),
            egg_band_boundary_maxima=sum(r["band_max_boundary"] for r in egg),
            egg_median_abs_128_vs_64_peak_difference_cpm=float(
                np.median(
                    [abs(r["band_max_hz"] - r["band_max_hz_64s"]) * 60 for r in egg]
                )
            )
            if egg
            else None,
            stage_counts=dict(
                collections.Counter(";".join(stages[name]) for name in paths)
            ),
            interpretation="Recording and channel counts; no independent-subject inference, no artifact acceptance or dose-relative association",
        )
        (out / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        (out / "environment.txt").write_text(
            "\n".join(
                sorted(
                    f"{d.metadata['Name']}=={d.version}"
                    for d in importlib.metadata.distributions()
                )
            ),
            encoding="utf-8",
        )
        report = [
            "# 原始独立通道的抗混叠与频谱描述",
            "",
            "## Material Passport",
            "",
            "- Origin Skill: academic-research-suite / experiment-agent",
            "- Origin Mode: run + validate",
            "- Verification: 工程合成验证后运行；生理伪迹验收和临床推断尚未完成",
            "",
            json.dumps(summary, ensure_ascii=False, indent=2),
            "",
            "全部E/N/C/P原始ECG100C/EGG100C通道分别处理，文件T排除。计数单位为文件、记录窗和通道窗，不是独立受试者。采用每条记录起点后的完整300秒不重叠窗；末段不足300秒只登记，不补齐，也不与其他记录拼接。记录起点未解释为给药时点，P等标签不自动代表已核验静息窗口。",
            "",
            "ECG 2000→250 Hz；EGG 2000→100→4 Hz，多相Kaiser抗混叠，beta8.6，线性边界延拓；每窗裁两端各10秒，保留280秒。通道独立，不从重复旧CSV或旧SQI中选通道。边缘延拓仅用于滤波边界，并非填补真实缺失；非有限原始窗拒绝计算，恒值窗不输出功率比。",
            "",
            "Welch采用周期Hann、逐段线性去趋势、50%重叠和原分段长度FFT，无零填充。EGG128秒为主描述（0.0078125 Hz，3个重叠段），64秒为预定敏感性；ECG8秒（0.125 Hz）。功率使用PSD在频带精确边界的线性插值积分。单位为头部mV的平方；尚未独立核验硬件标定。",
            "",
            "EGG宽频带0.0083–0.15 Hz、窄频带0.033–0.067 Hz。窄带比例是功率比例，不是正常胃节律时间占比；带内最大谱峰不是已经验证的胃起搏频率，可能反映漂移、运动或混杂。边界峰和64/128秒峰差用于描述估计敏感性，不作为事后选参数或排除规则。",
            "",
            "精确恒值段保留标记，不自动剔除；当前没有经过验证的生理QC阈值，因此计算成功不能称为临床可用。未做R峰检测/HRV、相位耦合、给药前后效应、生理–VAS关联或按独立受试者的显著性推断。",
            "",
            "逐通道窗表、每条原始记录对应的频率/PSD数组及尾段支持表均保存在私有目录。记录汇总取同记录各通道窗的中位数，仅用于作图；不合并原始波形，不将其作为临床结局。",
            "",
            "配置、全部输入哈希、源码及SciPy关键实现哈希、环境和测试日志已记录；源文件、旧CSV与既有VAS输出未修改。",
        ]
        (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        state["status"] = (
            "completed_descriptive_spectra"
            if not failures
            else "completed_with_file_failures"
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
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
