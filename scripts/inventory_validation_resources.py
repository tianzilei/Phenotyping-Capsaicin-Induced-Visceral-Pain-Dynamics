"""Inventory existing signal duration, planned windows and candidate resources.

No resampling of review windows, changes to pools, or new quality decisions.
"""

import json
import sys
import platform
import subprocess
import uuid
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from prepare_reanalysis_20260926 import ROOT, read, write, dump, sha


def time_segments(t):
    if len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError("Invalid actual Hb time")
    dt = float(np.median(np.diff(t)))
    cuts = np.r_[0, np.flatnonzero(np.diff(t) > 1.5 * dt) + 1, len(t)]
    return [(float(t[a]), float(t[b - 1])) for a, b in zip(cuts[:-1], cuts[1:])], dt


def available(intervals, a, b):
    return any(x <= a + 1e-9 and y >= b - 1e-9 for x, y in intervals)


def main():
    acq = ROOT / "08_outputs/reanalysis_20260926_20260927T141237Z_c57a7087/ecg_5db91f25"
    hb = ROOT / "08_outputs/hb_combined_20260927T161640Z_7b0bff85"
    baseline = ROOT / "08_outputs/reanalysis_20260926_20260927T141652Z_4008dbed"
    paths = [
        baseline / "reference_split_private.csv",
        baseline / "BaselineData_person_private.csv",
        acq / "record_audit_private.csv",
        acq / "features_private.csv",
        acq / "manifest.json",
        hb / "record_audit_private.csv",
        hb / "features_private.csv",
        hb / "manifest.json",
    ]
    out = (
        ROOT
        / "02_quality_control"
        / (
            "validation_resources_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    policy = dict(
        version="validation_resource_inventory_v1",
        duration_thresholds_seconds=[60, 128, 180, 256, 300],
        windows="fixed blocks 0-300,300-600,600-900,900-1200 seconds; also raw continuous capacity",
        Hb_duration="conservative observed first-to-last timestamp; no endpoint extrapolation; split gaps >1.5 median dt",
        ACQ_duration="selected segment point count / header sample rate; never concatenate segments",
        candidate_filter="existing A support, zero offset/drift; Hb mad6 guard2 coverage.9 ROI fraction.5",
        EGG="128/256 s spectral segments are descriptive availability, never physiological acceptance",
        review_pools_changed=False,
        review_windows_resampled=False,
        independence="pool membership is not proof of unexposed/independent validation; all signals previously algorithm-screened",
    )
    dump(out / "frozen_config.json", policy)
    inputs = {str(p): sha(p) for p in paths + [out / "frozen_config.json"]}
    # Verify current feature artifacts against their own immutable manifests.
    for folder in [acq, hb]:
        m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for name in ["record_audit_private.csv", "features_private.csv"]:
            if sha(folder / name) != m["outputs_sha256"][name]:
                raise ValueError("Selected artifact changed")
    split = {r["person_id"]: r for r in read(paths[0])}
    vas = {r["ID"]: r for r in read(paths[1])}
    if set(split) != set(vas) or len(split) != 215:
        raise ValueError("Roster mismatch")
    records = {}
    sources = {}
    by_acq = defaultdict(list)
    for r in read(acq / "record_audit_private.csv"):
        by_acq[r["person_id"]].append(r)
    for sid, rows in by_acq.items():
        for modality, label in [("ECG", "ECG100C"), ("EGG", "EGG100C")]:
            rr = [r for r in rows if r["label"] == label]
            if not rr:
                continue
            specs = {
                (
                    r["path"],
                    r["sha256"],
                    r["samples"],
                    r["sampling_hz"],
                    r["source_start_sample"],
                    r["source_end_sample"],
                )
                for r in rr
            }
            if len(specs) != 1:
                raise ValueError("Inconsistent channel time supports")
            r = rr[0]
            fs = float(r["sampling_hz"])
            duration = int(r["samples"]) / fs
            records[sid, modality] = dict(
                path=r["path"],
                sha256=r["sha256"],
                channels=len(rr),
                intervals=[(0.0, duration)],
                duration=duration,
                fs=fs,
                gaps=0,
                source_start=int(r["source_start_sample"]),
                source_end=int(r["source_end_sample"]),
            )
            sources[r["path"]] = r["sha256"]
    for i, r in enumerate(read(hb / "record_audit_private.csv"), 1):
        p = Path(r["path"])
        t = np.loadtxt(p, delimiter="\t", skiprows=35, usecols=0, encoding="utf-8-sig")
        intervals, dt = time_segments(t)
        if len(t) != int(r["samples"]) or abs(t[-1] - float(r["end"])) > 1e-8:
            raise ValueError("Hb time audit mismatch")
        records[r["person_id"], "Hb"] = dict(
            path=str(p),
            sha256=r["sha256"],
            channels=42,
            intervals=intervals,
            duration=float(t[-1] - t[0]),
            fs=1 / dt,
            gaps=len(intervals) - 1,
            source_start=0,
            source_end=len(t),
        )
        sources[str(p)] = r["sha256"]
        if i % 40 == 0:
            print("Hb actual time checked", i, flush=True)
    for p, digest in sources.items():
        if sha(p) != digest:
            raise ValueError("Source changed")
    rawrows = []
    blocks = []
    for sid, s in sorted(split.items()):
        for modality in ["ECG", "EGG", "Hb"]:
            r = records.get((sid, modality))
            intervals = r["intervals"] if r else []
            longest = max((b - a for a, b in intervals), default=0)
            planned = int(s["representative_block"])
            row = dict(
                person_id=sid,
                pool=s["pool"],
                modality=modality,
                has_record=bool(r),
                duration_s=r["duration"] if r else None,
                longest_continuous_s=longest,
                gaps=r["gaps"] if r else None,
                channels=r["channels"] if r else 0,
                path=r["path"] if r else "",
                sha256=r["sha256"] if r else "",
                selected_source_start_sample=r["source_start"] if r else None,
                selected_source_end_sample=r["source_end"] if r else None,
                fixed_300s_blocks=sum(
                    available(intervals, b * 300, (b + 1) * 300) for b in range(4)
                ),
                original_block=planned,
                original_block_complete=available(
                    intervals, planned * 300, (planned + 1) * 300
                ),
                independence_status="not_established_by_pool_label",
                annotation_status="not_annotated",
            )
            for threshold in policy["duration_thresholds_seconds"]:
                row[f"continuous_ge_{threshold}s"] = longest >= threshold - 1e-9
            rawrows.append(row)
            for block in range(4):
                a, b = block * 300, (block + 1) * 300
                numeric = all(
                    vas[sid].get(f"VAS_{minute}min", "") not in ["", "E", "T"]
                    and _finite(vas[sid][f"VAS_{minute}min"])
                    for minute in range(block * 5 + 1, block * 5 + 6)
                )
                blocks.append(
                    dict(
                        person_id=sid,
                        pool=s["pool"],
                        modality=modality,
                        block=block,
                        start_s=a,
                        end_s=b,
                        original_random_block=block == planned,
                        full_continuous_signal=available(intervals, a, b),
                        numeric_VAS_all_5=numeric,
                        signal_and_VAS=available(intervals, a, b) and numeric,
                    )
                )
    write(out / "people_modality_private.csv", rawrows)
    write(out / "fixed_windows_private.csv", blocks)
    candidates = defaultdict(set)
    spectral = defaultdict(set)
    e = pd.read_csv(acq / "features_private.csv", low_memory=False)
    e = e[(e.support_spec == "A") & (e.offset_s == 0) & (e.drift_ppm == 0)]
    for r in e.itertuples():
        if (
            r.metric in ["HR", "candidate_RR_RMSSD"]
            and r.algorithm_candidate_pass == True
            and pd.notna(r.value)
        ):
            candidates[r.metric].add((r.person_id, int(r.block)))
        elif r.metric == "EGG":
            seconds = int(r.welch_seconds)
            if pd.notna(r.segments) and r.segments >= 1:
                spectral[f"EGG_{seconds}s_any_clean_spectral_segment"].add(
                    (r.person_id, int(r.block))
                )
            if r.status == "descriptive_peak_unvalidated":
                spectral[f"EGG_{seconds}s_descriptive_peak"].add(
                    (r.person_id, int(r.block))
                )
    columns = [
        "person_id",
        "block",
        "support_spec",
        "offset_s",
        "drift_ppm",
        "mad",
        "guard_s",
        "coverage_threshold",
        "roi_fraction",
        "roi",
        "metric",
        "value",
        "algorithm_candidate_pass",
    ]
    hb_targets = set()
    for h in pd.read_csv(
        hb / "features_private.csv", usecols=columns, chunksize=150000
    ):
        h = h[
            (h.support_spec == "A")
            & (h.offset_s == 0)
            & (h.drift_ppm == 0)
            & (h.mad == 6)
            & (h.guard_s == 2)
            & (h.coverage_threshold == 0.9)
            & (h.roi_fraction == 0.5)
        ]
        for r in h.itertuples():
            target = f"{r.roi}_{r.metric}"
            hb_targets.add(target)
            if r.algorithm_candidate_pass == True and pd.notna(r.value):
                candidates[target].add((r.person_id, int(r.block)))
    for metric in ["HbO", "HbR"]:
        ss = [candidates[t] for t in sorted(hb_targets) if t.endswith("_" + metric)]
        candidates[metric + "_any_ROI"] = set().union(*ss)
        candidates[metric + "_all_11_ROIs"] = set.intersection(*ss)
    for seconds in [128, 256]:
        for suffix in ["any_clean_spectral_segment", "descriptive_peak"]:
            spectral.setdefault(f"EGG_{seconds}s_{suffix}", set())
    target_rows = []
    resource_rows = []
    for target, keys in {**candidates, **spectral}.items():
        modality = (
            "ECG"
            if target in ["HR", "candidate_RR_RMSSD"]
            else "EGG"
            if target.startswith("EGG_")
            else "Hb"
        )
        keys = {
            k
            for k in keys
            if available(
                records[k[0], modality]["intervals"], k[1] * 300, (k[1] + 1) * 300
            )
        }
        for sid, s in sorted(split.items()):
            bs = sorted(b for person, b in keys if person == sid)
            resource_rows.append(
                dict(
                    person_id=sid,
                    pool=s["pool"],
                    target=target,
                    blocks=";".join(map(str, bs)),
                    block_count=len(bs),
                    original_block_eligible=int(s["representative_block"]) in bs,
                    status="descriptive_spectral_availability_not_acceptance"
                    if modality == "EGG"
                    else "algorithm_candidate_not_independent_validation",
                )
            )
        for pool in [
            "all",
            "development",
            "sealed_validation",
            "application",
            "nondevelopment",
        ]:
            ids = {
                sid
                for sid, s in split.items()
                if pool == "all"
                or s["pool"] == pool
                or (pool == "nondevelopment" and s["pool"] != "development")
            }
            kk = {k for k in keys if k[0] in ids}
            anyids = {sid for sid, b in kk}
            original = {
                sid for sid, b in kk if int(split[sid]["representative_block"]) == b
            }
            target_rows.append(
                dict(
                    pool=pool,
                    target=target,
                    modality=modality,
                    people_any_eligible_fixed_block=len(anyids),
                    people_original_block_eligible=len(original),
                    people_2plus_blocks=sum(
                        sum(p == sid for p, b in kk) >= 2 for sid in anyids
                    ),
                    eligible_unique_person_blocks=len(kk),
                    zero_error_95_upper_if_any_all_independent_accepted=bound(
                        len(anyids)
                    ),
                    additional_independent_accepts_to_59=max(0, 59 - len(anyids)),
                )
            )
    write(out / "candidate_resources_private.csv", resource_rows)
    write(out / "candidate_capacity.csv", target_rows)
    rawsummary = []
    for pool in [
        "all",
        "development",
        "sealed_validation",
        "application",
        "nondevelopment",
    ]:
        for modality in ["ECG", "EGG", "Hb"]:
            rr = [
                r
                for r in rawrows
                if r["modality"] == modality
                and (
                    pool == "all"
                    or r["pool"] == pool
                    or (pool == "nondevelopment" and r["pool"] != "development")
                )
            ]
            rawsummary.append(
                dict(
                    pool=pool,
                    modality=modality,
                    pool_people=len(rr),
                    people_with_record=sum(r["has_record"] for r in rr),
                    people_original_block_complete=sum(
                        r["original_block_complete"] for r in rr
                    ),
                    people_any_complete_fixed_block=sum(
                        r["fixed_300s_blocks"] > 0 for r in rr
                    ),
                    fixed_block_count=sum(r["fixed_300s_blocks"] for r in rr),
                    **{
                        f"people_continuous_ge_{n}s": sum(
                            r[f"continuous_ge_{n}s"] for r in rr
                        )
                        for n in policy["duration_thresholds_seconds"]
                    },
                )
            )
    write(out / "duration_capacity.csv", rawsummary)
    both = []
    for sid, s in split.items():
        ac = records.get((sid, "ECG"))
        hh = records.get((sid, "Hb"))
        both.append(
            dict(
                person_id=sid,
                pool=s["pool"],
                has_both=bool(ac and hh),
                shared_nominal_300s_blocks=sum(
                    available(ac["intervals"], b * 300, (b + 1) * 300)
                    and available(hh["intervals"], b * 300, (b + 1) * 300)
                    for b in range(4)
                )
                if ac and hh
                else 0,
                timing_status="nominal_recording_origins_not_verified_synchrony",
            )
        )
    write(out / "paired_resources_private.csv", both)
    summary = dict(
        total_people=len(split),
        record_people={
            m: sum(r["has_record"] for r in rawrows if r["modality"] == m)
            for m in ["ECG", "EGG", "Hb"]
        },
        paired_people=sum(r["has_both"] for r in both),
        Hb_people_with_time_gaps=sum(
            r["gaps"] > 0 for (sid, m), r in records.items() if m == "Hb"
        ),
        annotation_status="not_annotated",
        pools_changed=False,
        reference_window_selection_changed=False,
        candidate_capacity_is_not_independent_validation=True,
        minimum_zero_error_n_95_upper_5pct=math.ceil(math.log(0.05) / math.log(0.95)),
    )
    dump(out / "summary.json", summary)
    lines = [
        "# 验证资源盘点",
        "",
        "逐人盘点现有记录、真实连续时间、原随机窗口及既有算法候选。未更改分池、未重抽窗口、未新增质量阈值。",
        "",
        "|分池|模态|池内人数|有记录|原预定五分钟完整|任一固定五分钟完整|",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in rawsummary:
        lines.append(
            f"|{r['pool']}|{r['modality']}|{r['pool_people']}|{r['people_with_record']}|{r['people_original_block_complete']}|{r['people_any_complete_fixed_block']}|"
        )
    lines += [
        "",
        "## 原封存池的算法候选资源",
        "",
        "|目标|原随机块合格人数|任一固定块合格人数|至少两块人数|",
        "|---|---:|---:|---:|",
    ]
    for r in target_rows:
        if r["pool"] == "sealed_validation" and (
            r["modality"] != "Hb" or r["target"].startswith(("HbO_", "HbR_"))
        ):
            lines.append(
                f"|{r['target']}|{r['people_original_block_eligible']}|{r['people_any_eligible_fixed_block']}|{r['people_2plus_blocks']}|"
            )
    lines += [
        "",
        "## 解释与使用范围",
        "",
        "ECG 与 EGG 分开计数但源自同一批 ACQ。ACQ 只使用已裁定连续片段，Hb 读取全部实际时间并分隔缺口；Hb 时长保守取首末时间差，不外推一个采样间隔。60/128/180/256 秒仅盘点原始时长，不代表这些短窗口已完成目标验证。",
        "算法候选使用既有完整五分钟 VAS 支持、名义零偏移和冻结主参数。Hb 各 ROI 分别列出；any ROI 不等于全部 ROI 均可用。EGG 的 clean segment/描述峰只表示谱计算条件，不表示真实胃节律通过。",
        "全 215 人中无当前纳入源者记为“无当前选定记录”，不推断从未采集；原始文件缺失与来源归属排除不能混同。",
        "原封存和 application 是历史分池标签，所有现有信号已参与自动处理且已有汇总查看；尚未审计全部人工/调参暴露历史，不能据标签承诺独立验证。nondevelopment 仅为资源合计，未转移 application 人员。",
        "原随机窗口方案和“从可用窗口重新随机”的方案针对不同抽样总体。后者只能在另行版本化方案下考虑，不按质量好坏或关联大小挑选，也不能将本表的合格人数直接当验证通过人数。",
        "零错误时单目标一侧 95% 上限≤5% 至少需要59个独立且算法接受的受试者。表中容量计算是理想上限，未观测人工错误；有错误时需要更多样本。",
        "逐人文件：people_modality_private.csv、fixed_windows_private.csv、candidate_resources_private.csv、paired_resources_private.csv；聚合文件：duration_capacity.csv、candidate_capacity.csv。",
    ]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    dump(
        out / "manifest.json",
        dict(
            created_utc=datetime.now(timezone.utc).isoformat(),
            summary=summary,
            input_sha256=inputs,
            sources_sha256=sources,
            code_sha256={str(Path(__file__)): sha(__file__)},
            python=sys.version,
            numpy=np.__version__,
            pandas=pd.__version__,
            platform=platform.platform(),
            git_revision=subprocess.check_output(
                ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
                text=True,
            ).strip(),
            outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
        ),
    )
    print(out)
    print(json.dumps(summary))


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


def bound(n):
    return 1 - 0.05 ** (1 / n) if n else None


if __name__ == "__main__":
    main()
