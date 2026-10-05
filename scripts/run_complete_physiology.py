"""Current complete-VAS cohort: source verification, clock audit and NeuroKit2 ECG."""

import collections
import csv
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
import uuid
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.sync_verification import complete_vas, cluster_edges, audit_offsets
from path_resolver import resolve_external_path, execution_config, relocation_evidence


def read(p):
    with Path(p).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(p, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with Path(p).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def main():
    import bioread
    import numpy as np

    cp = execution_config(ROOT / "config/physiology_complete_v2.json")
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    out = (
        ROOT
        / "08_outputs"
        / (
            "complete_physiology_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    print(out, flush=True)
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "inclusion_private.csv")],
        cwd=ROOT,
        check=True,
    )
    wave = ROOT / cfg["waveform_run"]
    event = ROOT / cfg["event_run"]
    inputs = [
        cp,
        ROOT / cfg["vas_input"],
        ROOT / cfg["mapping"],
        wave / "run_manifest.json",
        wave / "digital_events_private.csv",
        wave / "channels_private.csv",
        event / "protocol_events_private.csv",
        Path(__file__),
        ROOT / "src/capsaicin/sync_verification.py",
    ]
    inputs += relocation_evidence() + [ROOT / "scripts/path_resolver.py"]
    state = dict(
        status="running",
        created_utc=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(),
        revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        inputs_sha256={str(p): sha(p) for p in inputs},
        signals_sha256={},
        software={},
    )
    (out / "frozen_config.json").write_text(
        cp.read_text(encoding="utf-8"), encoding="utf-8"
    )

    def save():
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    save()
    for p in ["bioread", "numpy", "scipy", "neurokit2", "pandas"]:
        try:
            state["software"][p] = importlib.metadata.version(p)
        except importlib.metadata.PackageNotFoundError:
            state["software"][p] = None
    window_seconds = int(
        os.environ.get("CAPSAICIN_WINDOW_SECONDS", cfg["ecg"]["window_seconds"])
    )
    if window_seconds <= 0:
        raise ValueError("CAPSAICIN_WINDOW_SECONDS must be positive")
    rows = read(ROOT / cfg["vas_input"])
    ids = [r["ID"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source IDs")
    included = {r["ID"] for r in rows if complete_vas(r)}
    ledger = [
        dict(
            subject_id=r["ID"],
            included=complete_vas(r),
            reason="complete_20_numeric"
            if complete_vas(r)
            else "incomplete_or_invalid",
            invalid_cells=";".join(
                f"{i}:{r.get(f'VAS_{i}min', '')}"
                for i in range(1, 21)
                if not complete_vas(
                    {f"VAS_{j}min": r.get(f"VAS_{i}min", "") for j in range(1, 21)}
                )
            ),
        )
        for r in rows
    ]
    write(out / "inclusion_private.csv", ledger)
    write(out / "complete_vas_private.csv", [r for r in rows if r["ID"] in included])
    mapping = [
        r
        for r in read(ROOT / cfg["mapping"])
        if r["current_subject_id"] in included
        and r["stage"] in cfg["allowed_stages"]
        and not Path(r["path"]).name.startswith("._")
    ]
    owners = collections.defaultdict(set)
    for r in mapping:
        owners[r["path"]].add(r["current_subject_id"])
    manifest = json.loads((wave / "run_manifest.json").read_text())
    for name in ("channels_private.csv", "digital_events_private.csv"):
        if sha(wave / name) != manifest["outputs_sha256"][name]:
            raise ValueError("Prior waveform audit changed")
    edges = collections.defaultdict(list)
    protocols = collections.defaultdict(list)
    for r in read(wave / "digital_events_private.csv"):
        edges[(r["path"], r["channel"])].append(r)
    for r in read(event / "protocol_events_private.csv"):
        protocols[r["path"]].append(r)
    channels = read(wave / "channels_private.csv")
    records = []
    sync = []
    matches = []
    candidates = []
    native = []
    failures = []
    features = []
    annotations = []
    starts = time.monotonic()
    ecg_paths = sorted(
        {r["path"] for r in mapping if r["extension"] == ".acq" and r["stage"] == "E"}
    )
    # Clock audit does not need NeuroKit2 and is completed before ECG processing.
    for n, name in enumerate(ecg_paths, 1):
        try:
            p = resolve_external_path(name)
            if p is None:
                raise FileNotFoundError(name)
            digest = sha(p)
            if digest != manifest["signals_sha256"][name]:
                raise ValueError("Raw source hash changed")
            state["signals_sha256"][name] = digest
            with p.open("rb") as f:
                reader = bioread.reader.Reader(f)
                reader._read_headers()
                d = reader.datafile
            for mark in d.event_markers:
                annotations.append(dict(path=name, marker=str(mark)))
            subject = next(iter(owners[name])) if len(owners[name]) == 1 else ""
            row = dict(
                subject_id=subject,
                path=name,
                unique_owner=len(owners[name]) == 1,
                digital_channels=sum("Digital" in c.name for c in d.channels),
                acq_markers=len(d.event_markers),
                duration_s=min(
                    c.point_count / c.samples_per_second for c in d.channels
                ),
                raw_hash_verified=True,
            )
            records.append(row)
            related = [r for r in mapping if r["path"] == name]
            dates = {r["date"] for r in related}
            pp = sorted(
                {
                    r["path"]
                    for r in mapping
                    if r["current_subject_id"] == subject
                    and r["stage"] == "E"
                    and r["date"] in dates
                    and r["path"] in protocols
                }
            )
            eg = [(key, value) for key, value in edges.items() if key[0] == name]
            if not eg or not pp:
                sync.append(
                    dict(
                        subject_id=subject,
                        path=name,
                        status="no_recorded_digital_edges"
                        if not eg
                        else "no_matched_fnirs_events",
                        verified=False,
                    )
                )
            for key, group in eg:
                native.extend(dict(subject_id=subject, **r) for r in group)
                a = [
                    x[0]
                    for x in cluster_edges(
                        [float(r["time_from_recording_start_s"]) for r in group],
                        cfg["synchronization"]["edge_cluster_seconds"],
                    )
                ]
                for fp in pp:
                    b = [float(r["start_label_seconds"]) for r in protocols[fp]]
                    result = audit_offsets(a, b, cfg["synchronization"])
                    pair_id = f"{subject}:{len(sync)}"
                    sync.append(
                        dict(
                            subject_id=subject,
                            path=name,
                            fnirs_path=fp,
                            channel=key[1],
                            pair_id=pair_id,
                            native_edges=len(group),
                            edge_clusters=len(a),
                            fnirs_events=len(b),
                            verified=False,
                            **{
                                k: v
                                for k, v in result.items()
                                if k not in ("pairs", "candidates")
                            },
                        )
                    )
                    for rank, c in enumerate(result["candidates"]):
                        candidates.append(
                            dict(
                                pair_id=pair_id,
                                rank=rank + 1,
                                **{k: v for k, v in c.items() if k != "pairs"},
                            )
                        )
                    for i, j in result["pairs"]:
                        matches.append(
                            dict(
                                pair_id=pair_id,
                                acq_cluster_index=i,
                                fnirs_event_index=j,
                                acq_s=a[i],
                                fnirs_s=b[j],
                                candidate_residual_s=b[j] - a[i] - result["offset_s"],
                                event_identity_verified=False,
                            )
                        )
        except Exception as exc:
            failures.append(dict(path=name, phase="clock_audit", error=str(exc)))
        if n % 10 == 0:
            print(f"Clock headers/hash {n}/{len(ecg_paths)}", flush=True)
            save()
    for name, data in [
        ("recordings_private.csv", records),
        ("sync_private.csv", sync),
        ("offset_candidates_private.csv", candidates),
        ("matched_events_private.csv", matches),
        ("native_edges_private.csv", native),
        ("acq_annotations_private.csv", annotations),
    ]:
        write(out / name, data)
    save()
    print(
        "Clock audit complete",
        dict(collections.Counter(r["status"] for r in sync)),
        flush=True,
    )
    if state["software"]["neurokit2"]:
        import neurokit2 as nk
        from capsaicin.signal_spectra import resample_exact
        import warnings

        arrdir = out / "rpeaks_private"
        arrdir.mkdir()
        for number, name in enumerate(ecg_paths, 1):
            if time.monotonic() - starts > cfg["timeout_seconds"]:
                failures.append(
                    dict(path=name, phase="timeout", error="Frozen one-hour limit")
                )
                break
            if name not in state["signals_sha256"]:
                continue
            try:
                p = resolve_external_path(name)
                if p is None:
                    raise FileNotFoundError(name)
                with p.open("rb") as f:
                    reader = bioread.reader.Reader(f)
                    reader._read_headers()
                    reader._read_data(None, bioread.reader.CHUNK_SIZE)
                    d = reader.datafile
                sid = next(iter(owners[name])) if len(owners[name]) == 1 else ""
                for k, ch in enumerate(d.channels):
                    if ch.name != "ECG100C":
                        continue
                    try:
                        if ch.units != "mV":
                            raise ValueError("Unverified ECG unit")
                        raw = np.asarray(ch.data, dtype=float)
                        if not np.isfinite(raw).all() or np.ptp(raw) == 0:
                            raise ValueError("Nonfinite/constant: no filling")
                        fs = cfg["ecg"]["target_rate_hz"]
                        y = resample_exact(raw, ch.samples_per_second, fs)
                        inverted, inversion = nk.ecg_invert(
                            y, sampling_rate=fs, force=False
                        )
                        clean = nk.ecg_clean(
                            inverted,
                            sampling_rate=fs,
                            method=cfg["ecg"]["clean_method"],
                        )
                        _, info = nk.ecg_peaks(
                            clean,
                            sampling_rate=fs,
                            method=cfg["ecg"]["peak_method"],
                            correct_artifacts=False,
                        )
                        peaks = np.asarray(info["ECG_R_Peaks"], dtype=int)
                        np.savez_compressed(
                            arrdir / f"record_{number:03d}_channel_{k}.npz",
                            rpeaks_samples=peaks,
                            sampling_rate=fs,
                            inverted=inversion,
                        )
                        for w in range(len(y) // (window_seconds * fs)):
                            start = w * window_seconds * fs
                            end = start + window_seconds * fs
                            local = peaks[(peaks >= start) & (peaks < end)] - start
                            rr = np.diff(local) / fs
                            entry = dict(
                                subject_id=sid,
                                path=name,
                                channel=k,
                                window_index=w,
                                start_s=start / fs,
                                end_s=end / fs,
                                frame="recording_relative_length_aligned_minute"
                                if window_seconds == 60
                                else "recording_relative_not_dose",
                                inverted=inversion,
                                beat_count=len(local),
                                sampling_rate_hz=fs,
                                window_seconds=window_seconds,
                                minute_index=w + 1,
                                status="qc_failed",
                                qc_pass=False,
                                association_eligible=False,
                            )
                            try:
                                if len(rr) < 2:
                                    raise ValueError("Insufficient peaks")
                                with warnings.catch_warnings(record=True) as warns:
                                    q = nk.ecg_quality(
                                        clean[start:end],
                                        rpeaks=local,
                                        sampling_rate=fs,
                                        method="zhao2018",
                                        approach="fuzzy",
                                    )
                                    bad = np.mean(
                                        (rr < cfg["ecg"]["rr_min_seconds"])
                                        | (rr > cfg["ecg"]["rr_max_seconds"])
                                    )
                                    art, corrected = nk.signal_fixpeaks(
                                        local,
                                        sampling_rate=fs,
                                        method="Kubios",
                                        iterative=False,
                                    )
                                    corrected_n = sum(
                                        len(art.get(t, []))
                                        for t in (
                                            "ectopic",
                                            "missed",
                                            "extra",
                                            "longshort",
                                        )
                                    )
                                    fraction = corrected_n / len(local)
                                    entry.update(
                                        quality=str(q),
                                        abnormal_rr_fraction=float(bad),
                                        flagged_beat_fraction=fraction,
                                        mean_hr_bpm=float(60 / np.mean(rr)),
                                        warning_count=len(warns),
                                    )
                                    accepted = (
                                        q in ("Excellent", "Barely acceptable")
                                        and bad == 0
                                        and fraction
                                        <= cfg["ecg"]["maximum_correction_fraction"]
                                    )
                                    entry["qc_pass"] = bool(accepted)
                                    if accepted:
                                        hrv = nk.hrv_time(
                                            local, sampling_rate=fs, show=False
                                        ).iloc[0]
                                        entry.update(
                                            {
                                                metric: float(hrv[metric])
                                                for metric in cfg["ecg"]["hrv_metrics"]
                                            }
                                        )
                                        entry["status"] = (
                                            "algorithm_screened_recording_relative"
                                        )
                                    # No excision or correction of RR: no artificial adjacency.
                            except Exception as exc:
                                entry["error"] = str(exc)
                            features.append(entry)
                    except Exception as exc:
                        failures.append(
                            dict(
                                path=name,
                                channel=k,
                                phase="ecg_channel",
                                error=str(exc),
                            )
                        )
            except Exception as exc:
                failures.append(dict(path=name, phase="ecg_record", error=str(exc)))
            write(out / "ecg_windows_private.csv", features)
            write(out / "failures_private.csv", failures)
            save()
            print(
                f"NeuroKit2 {number}/{len(ecg_paths)}; windows {len(features)}",
                flush=True,
            )
    else:
        failures.append(
            dict(
                phase="dependency",
                error="NeuroKit2 unavailable; no substitute estimator used",
            )
        )
    summary = dict(
        candidate_vas=len(rows),
        complete_vas=len(included),
        excluded_vas=len(rows) - len(included),
        challenge_acq=len(ecg_paths),
        raw_verified=len(records),
        clock_status=dict(collections.Counter(r["status"] for r in sync)),
        verified_vas_event_anchors=0,
        ecg_channel_windows=len(features),
        ecg_algorithm_qc_pass=sum(r["qc_pass"] for r in features),
        association_status="not_estimable_without_verified_VAS_minute_anchor",
        failures=len(failures),
    )
    write(out / "failures_private.csv", failures)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report = [
        "# 完整 VAS 队列电生理处理与同步核验",
        "",
        "## Material Passport",
        "",
        "- Origin Skill: academic-research-suite / experiment-agent",
        "- Origin Mode: run + validate",
        "- Verification: 本次原始文件哈希及事件匹配已执行；科学验收按逐项状态列示",
        "",
        "```json",
        json.dumps(summary, ensure_ascii=False, indent=2),
        "```",
        "",
        "纳入依据为 1–20 分钟 20 个有效数值，合法零值保留；E/T、空缺与非有限值排除。来源和旧结果未修改。",
        "各设备同程序共时控制按用户确认记录。TTL 原始电平、短边沿簇及所有候选 offset 均保留；一对一顺序匹配允许缺失。周期事件存在相差整分钟的候选解时，不选残差最小者宣称已同步。",
        "记录开始标记不是给药标记。共享事件语义不能独立确定评分分钟编号。其他课题资料包不提供本队列逐例核验。",
        "ECG 使用 NeuroKit2 清洗、极性检测、R 峰检测、Zhao2018 质量分类和 Kubios 异常搏动标记；不实际插补或删除间隔。全部通道和窗口保存。HRV 为通过算法筛查的记录相对描述，非经人工裁定的临床 NN。",
        "NeuroKit2 ECG 算法不直接适用于胃电。EGG 保留既有原始频谱诊断，本次未把 ECG 处理冒称 EGG 专用算法。",
        "关联未估计：尚无同时具备已核验 VAS 分钟事件锚点与质量合格窗口的分析输入，不能把未运行写成零效应或不显著。",
        "局限：完整者及可用信号的选择、重复窗口非独立、算法质量筛查非临床标注、周期时钟错位；没有使用 VAS 相关性挑选同步或通道。",
    ]
    (out / "REPORT.md").write_text("\n\n".join(report) + "\n", encoding="utf-8")
    state.update(
        status="completed_processing_association_not_estimable",
        finished_utc=datetime.now(timezone.utc).isoformat(),
        summary=summary,
    )
    state["outputs_sha256"] = {
        str(p.relative_to(out)): sha(p)
        for p in out.rglob("*")
        if p.is_file() and p.name != "run_manifest.json"
    }
    save()
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
