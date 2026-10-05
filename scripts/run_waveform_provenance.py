"""Read raw waveforms, describe numeric quality, and compare historical exports."""

import collections
import csv
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import bioread
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.waveform_audit import describe, agreement
from audit_signal_readiness import sha, write
from path_resolver import resolve_external_path, execution_config, relocation_evidence


def main():
    cp = execution_config(ROOT / "config/waveform_provenance_v1.json")
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    prior = ROOT / cfg["prior_audit"] / "run_manifest.json"
    prior_manifest = json.loads(prior.read_text(encoding="utf-8"))
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
    exports = collections.defaultdict(list)
    for p in Path(cfg["legacy_csv_directory"]).glob("*.csv"):
        if not p.name.startswith("._"):
            exports[p.stem.lower()].append(p)
    out = (
        ROOT
        / "02_quality_control"
        / (
            "waveform_provenance_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "channels_private.csv")],
        cwd=ROOT,
        check=True,
    )
    sources = [
        cp,
        mapping,
        prior,
        Path(__file__).resolve(),
        ROOT / "src/capsaicin/waveform_audit.py",
        ROOT / "scripts/audit_signal_readiness.py",
    ]
    legacy_root = Path("D:/capsaicin旧版/analysis")
    sources += relocation_evidence() + [ROOT / "scripts/path_resolver.py"]
    sources += [
        legacy_root / p
        for p in [
            "config/constants.json",
            "constants.py",
            "data_loader.py",
            "ecg_egg/preprocessing.py",
            "ecg_egg/features.py",
            "cli.py",
        ]
    ]
    state = dict(
        status="running",
        created_utc=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(),
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        inputs_sha256={str(p): sha(p) for p in sources},
        signals_sha256={},
        exports_sha256={},
    )
    rows, duplicates, comparisons, events, failures = [], [], [], [], []
    started = time.monotonic()
    print(out, flush=True)

    def save():
        for name, values in [
            ("channels_private.csv", rows),
            ("duplicates_private.csv", duplicates),
            ("comparisons_private.csv", comparisons),
            ("digital_events_private.csv", events),
            ("failures_private.csv", failures),
        ]:
            write(out / name, values)
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    try:
        for number, name in enumerate(paths, 1):
            if time.monotonic() - started > cfg["timeout_seconds"]:
                raise TimeoutError("Time budget reached; partial output retained")
            p = resolve_external_path(name)
            try:
                if p is None:
                    raise FileNotFoundError(f"unresolved external path: {name}")
                digest = sha(p)
                if digest != prior_manifest["signals_sha256"][name]:
                    raise ValueError("Raw input changed since prior audit")
                state["signals_sha256"][name] = digest
                with p.open("rb") as handle:
                    reader = bioread.reader.Reader(handle)
                    reader._read_headers()
                    reader._read_data(None, bioread.reader.CHUNK_SIZE)
                    data = reader.datafile
                arrays = []
                for k, channel in enumerate(data.channels):
                    x = np.asarray(channel.data)
                    if x.ndim != 1 or len(x) != channel.point_count:
                        raise ValueError("Incomplete channel data")
                    rate = float(channel.samples_per_second)
                    r = dict(
                        path=name,
                        channel=k,
                        label=channel.name,
                        units=channel.units,
                        sampling_rate_hz=rate,
                        observed_span_s=(len(x) - 1) / rate,
                    )
                    r.update(describe(x, rate))
                    rows.append(r)
                    arrays.append(x)
                    if channel.name.startswith("Digital"):
                        # Exact transitions only: no threshold, no clinical event label.
                        edges = (
                            np.flatnonzero(
                                np.isfinite(x[1:])
                                & np.isfinite(x[:-1])
                                & (x[1:] != x[:-1])
                            )
                            + 1
                        )
                        for at in edges:
                            events.append(
                                dict(
                                    path=name,
                                    channel=k,
                                    sample=int(at),
                                    time_from_recording_start_s=float(at / rate),
                                    previous_native=float(x[at - 1]),
                                    next_native=float(x[at]),
                                    interpretation="unassigned_device_transition",
                                )
                            )
                for a in range(len(arrays)):
                    for b in range(a + 1, len(arrays)):
                        if (
                            data.channels[a].samples_per_second
                            == data.channels[b].samples_per_second
                            and arrays[a].shape == arrays[b].shape
                            and np.array_equal(arrays[a], arrays[b], equal_nan=True)
                        ):
                            duplicates.append(
                                dict(
                                    path=name,
                                    channel_a=a,
                                    channel_b=b,
                                    label_a=data.channels[a].name,
                                    label_b=data.channels[b].name,
                                    units_a=data.channels[a].units,
                                    units_b=data.channels[b].units,
                                    identical_full_vector=True,
                                )
                            )
                for suffix, label in [("", "ECG100C"), ("_egg", "EGG100C")]:
                    for exported in exports.get(p.stem.lower() + suffix, []):
                        state["exports_sha256"][str(exported)] = sha(exported)
                        header = next(csv.reader(exported.open(encoding="utf-8-sig")))
                        y = np.loadtxt(
                            exported,
                            delimiter=",",
                            skiprows=1,
                            ndmin=2,
                            encoding="utf-8-sig",
                        )
                        indices = [
                            k for k, c in enumerate(data.channels) if c.name == label
                        ]
                        schema = len(header) == len(indices) == y.shape[1] and all(
                            h == label or h.startswith(label + ".") for h in header
                        )
                        for stride in cfg["comparison_strides"]:
                            for offset in cfg["comparison_offsets"]:
                                tests = (
                                    [
                                        agreement(
                                            arrays[k],
                                            y[:, j],
                                            stride,
                                            offset,
                                            cfg["absolute_tolerance_native_mV"],
                                        )
                                        for j, k in enumerate(indices)
                                    ]
                                    if schema
                                    else []
                                )
                                eligible = bool(tests) and all(
                                    t["eligible"] for t in tests
                                )
                                comparisons.append(
                                    dict(
                                        path=name,
                                        export_path=str(exported),
                                        modality=label,
                                        schema_matches=schema,
                                        raw_samples=len(arrays[indices[0]])
                                        if indices
                                        else 0,
                                        csv_rows=len(y),
                                        csv_columns=y.shape[1],
                                        stride=stride,
                                        offset=offset,
                                        eligible=eligible,
                                        full_vector_matches=eligible
                                        and all(t["matches"] for t in tests),
                                        max_abs_difference=max(
                                            t["max_abs_difference"] for t in tests
                                        )
                                        if eligible
                                        else "",
                                        inferred_rate_hz=data.channels[
                                            indices[0]
                                        ].samples_per_second
                                        / stride
                                        if indices
                                        else "",
                                        raw_variable=any(
                                            np.ptp(arrays[k]) > 0 for k in indices
                                        ),
                                    )
                                )
            except Exception as exc:
                failures.append(dict(path=name, error=f"{type(exc).__name__}: {exc}"))
            if number % 25 == 0 or number == len(paths):
                save()
                print(
                    f"{number}/{len(paths)} files; failures={len(failures)}", flush=True
                )
        matched = [r for r in comparisons if r["full_vector_matches"]]
        summary = dict(
            files_planned=len(paths),
            files_read=len({r["path"] for r in rows}),
            failures=len(failures),
            channels=len(rows),
            nonfinite_values=sum(r["nonfinite"] for r in rows),
            whole_constant_channels=sum(r["whole_constant"] for r in rows),
            duplicate_pairs=len(duplicates),
            duplicate_files=len({r["path"] for r in duplicates}),
            duplicate_label_pairs=dict(
                collections.Counter(
                    r["label_a"] + " / " + r["label_b"] for r in duplicates
                )
            ),
            digital_transitions=len(events),
            legacy_exports_compared=len({r["export_path"] for r in comparisons}),
            legacy_exports_matching=len({r["export_path"] for r in matched}),
            matching_stride_offset=dict(
                collections.Counter(f"{r['stride']}/{r['offset']}" for r in matched)
            ),
            matches_with_variable_channel=sum(r["raw_variable"] for r in matched),
            channels_by_label=dict(collections.Counter(r["label"] for r in rows)),
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
            "# 原始ACQ波形与旧CSV来源核查",
            "",
            "- Origin Skill: academic-research-suite / experiment-agent",
            "- Origin Mode: run + validate",
            "- Verification: 数值来源与工程描述；尚非生理伪迹验收",
            "",
            json.dumps(summary, ensure_ascii=False, indent=2),
            "",
            "范围：E/N/C/P已映射文件，文件名T排除；记录和通道是计数单位，不等于独立受试者。时间仅相对记录起点，未把数字边沿解释为给药。完整原始文件哈希与上次审计比对，旧处理代码只读未执行。",
            "",
            "样本比较：同名CSV完整向量，对应ECG100C或EGG100C通道顺序，绝对容差1e-6 mV；预定步长1/8、起点0/1。匹配仅证明此导出与原始样本的一致性；不证明受试者/访视身份、硬件物理标定或伪迹合格。恒值通道的一致性较弱，另外列出有变化通道的匹配。",
            "",
            "旧源代码：analysis/config/constants.json固定fs=250，data_loader.load_signal读取CSV不重采样，features.build_feature_matrix默认该频率传入预处理。若旧CSV经全量比对等同未降采样的2000 Hz原始向量，默认旧流程的时间尺度与当前原始文件不一致；尚不能证明所有历史结果使用了该代码版本或默认参数，不能按8倍直接修补非线性特征，应在原始采样率和新配置下重新提取。",
            "",
            "另一个确定的代码问题：fs//4在250 Hz时为62，实际输出250/62≈4.03226 Hz而非4 Hz；旧代码硬标4 Hz。ECG/EGG方法稿与源实现还须逐项核对。",
            "",
            "精确恒值、非有限和重复通道属于基础信号描述。它们不能替代运动、饱和、R峰准确率、有效时长验收；未据此生成HRV、胃谱结论或生理–VAS关联。重复通道不得当作独立导联增大信息量。",
            "",
            "所有个体路径、逐通道表、完整比较及数字边沿在私有输出目录；源信号、旧CSV及旧结果均未修改。",
        ]
        (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        state["status"] = (
            "completed_numeric_audit"
            if not failures
            else "completed_with_read_failures"
        )
    except Exception as exc:
        state.update(status="failed", error=str(exc))
        raise
    finally:
        save()
        state["outputs_sha256"] = {
            p.name: sha(p)
            for p in out.iterdir()
            if p.is_file() and p.name != "run_manifest.json"
        }
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
