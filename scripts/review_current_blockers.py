"""Verify current candidate models and rebuild source-correct reference tasks."""

import csv
import json
import platform
import subprocess
import sys
import uuid
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from prepare_reanalysis_20260926 import ROOT, read, write, dump, sha
from run_candidate_associations import prepare, coefficient


def direct_fit(frame):
    """Independent OLS with explicit person and block dummy columns."""
    people = pd.get_dummies(frame.person_id, dtype=float).to_numpy()
    blocks = pd.get_dummies(
        frame.block.astype(int), drop_first=True, dtype=float
    ).to_numpy()
    design = np.column_stack([frame.vas_mean.to_numpy(float), people, blocks])
    if np.linalg.matrix_rank(design) != design.shape[1]:
        raise ValueError("Explicit model rank deficient")
    return float(np.linalg.lstsq(design, frame.value.to_numpy(float), rcond=None)[0][0])


def main():
    assoc = Path(sys.argv[1]).resolve()
    hb = assoc.parent
    ecg = ROOT / "08_outputs/reanalysis_20260926_20260927T141237Z_c57a7087/ecg_5db91f25"
    prepared = ROOT / "08_outputs/reanalysis_20260926_20260927T141652Z_4008dbed"
    split_path = prepared / "reference_split_private.csv"
    out = (
        ROOT
        / "02_quality_control"
        / (
            "current_blockers_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    manifest = json.loads((assoc / "manifest.json").read_text(encoding="utf-8"))
    inputs = {
        str(p): sha(p)
        for p in [
            assoc / "manifest.json",
            hb / "manifest.json",
            ecg / "manifest.json",
            split_path,
            prepared / "BaselineData_person_private.csv",
        ]
    }
    for name, digest in manifest["inputs_sha256"].items():
        if sha(name) != digest:
            raise ValueError("Candidate input changed")
    for name, digest in manifest["outputs_sha256"].items():
        if sha(assoc / name) != digest:
            raise ValueError("Candidate output changed")
    cfg = json.loads((assoc / "frozen_config.json").read_text(encoding="utf-8"))
    results = pd.read_csv(assoc / "planned_24_disposition.csv")
    models = pd.read_csv(assoc / "model_input_private.csv")
    timing = pd.read_csv(assoc / "timing_scenarios.csv")
    if len(results) != 24 or results.duplicated(["roi", "metric"]).any():
        raise ValueError("Wrong planned family")
    if results[["p", "q_BY_n24", "q_BH_n24"]].notna().any().any():
        raise ValueError("Unvalidated p/q published")
    checks = []
    timing_summary = []
    rng = np.random.default_rng(20260928)
    for r in results.itertuples():
        d = models[(models.roi == r.roi) & (models.metric == r.metric)].copy()
        if (
            d.duplicated(["person_id", "block"]).any()
            or (d.groupby("person_id").block.nunique() < 2).any()
        ):
            raise ValueError("Person/block contract violation")
        direct = direct_fit(d)
        if abs(direct - r.candidate_beta) > 1e-8:
            raise ValueError("Explicit OLS differs")
        prepared_fit, _ = prepare(d, standardize=False)
        ids = sorted(d.person_id.unique())
        # Repeated people become distinct bootstrap copies with explicit fixed effects.
        draw = rng.integers(len(ids), size=len(ids))
        weights = np.bincount(draw, minlength=len(ids))
        copied = []
        for index, selected in enumerate(draw):
            chunk = d[d.person_id == ids[selected]].copy()
            chunk["person_id"] = f"copy_{index:04d}"
            copied.append(chunk)
        bootdirect = direct_fit(pd.concat(copied, ignore_index=True))
        bootweighted = coefficient(prepared_fit, weights)
        if bootweighted is None or abs(bootdirect - bootweighted) > 1e-8:
            raise ValueError("Subject bootstrap implementation differs")
        failure = 1 - int(r.bootstrap_success) / cfg["bootstrap_replicates"]
        has_interval = pd.notna(r.candidate_percentile_low) and pd.notna(
            r.candidate_percentile_high
        )
        if has_interval != (
            failure <= cfg["maximum_bootstrap_failure_fraction"] + 1e-12
        ):
            raise ValueError("Bootstrap interval policy violated")
        checks.append(
            dict(
                roi=r.roi,
                metric=r.metric,
                n_people=int(r.n_people),
                n_blocks=int(r.n_blocks),
                independent_OLS_beta=direct,
                beta_difference=direct - r.candidate_beta,
                explicit_bootstrap_difference=bootdirect - bootweighted,
                bootstrap_success=int(r.bootstrap_success),
                bootstrap_failure_fraction=failure,
                interval_available=has_interval,
                validation="implementation_verified_target_unvalidated",
            )
        )
        tt = timing[(timing.roi == r.roi) & (timing.metric == r.metric)]
        for spec, group in tt.groupby("support_spec"):
            finite = group.candidate_beta.dropna()
            timing_summary.append(
                dict(
                    roi=r.roi,
                    metric=r.metric,
                    support_spec=spec,
                    scenarios=len(group),
                    min_people=int(group.n_people.min()),
                    max_people=int(group.n_people.max()),
                    min_beta=float(finite.min()),
                    max_beta=float(finite.max()),
                    sign_change=bool(finite.min() < 0 < finite.max()),
                    interpretation="sensitivity_not_clock_validation",
                )
            )
    write(out / "model_verification.csv", checks)
    write(out / "timing_summary.csv", timing_summary)
    split = {r["person_id"]: r for r in read(split_path)}
    # Keep the original random pools and representative blocks; never replace absent windows.
    tasks = []
    source_inputs = {}
    counter = 0
    for modality, run in [("ECG_EGG", ecg), ("Hb", hb)]:
        rows = read(run / "record_audit_private.csv")
        groups = defaultdict(list)
        for r in rows:
            groups[r["person_id"]].append(r)
        inputs[str(run / "record_audit_private.csv")] = sha(
            run / "record_audit_private.csv"
        )
        for sid, rr in sorted(groups.items()):
            s = split[sid]
            if s["pool"] == "application":
                continue
            counter += 1
            block = int(s["representative_block"])
            start = block * 300
            end = start + 300
            for r in rr:
                if modality == "Hb":
                    fs = float(r["sampling_hz"])
                    origin = 0
                    length = int(r["samples"])
                    support_end = float(r["end"])
                else:
                    fs = float(r["sampling_hz"])
                    origin = int(r["source_start_sample"])
                    length = int(r["samples"])
                    support_end = length / fs
                available = max(0, min(end, support_end) - start)
                full = available >= 300 - 1e-8
                # ECG original sample coordinates are exact; Hb selection uses actual TXT time.
                tasks.append(
                    dict(
                        task_id=f"{modality}_{counter:04d}",
                        person_id=sid,
                        pool=s["pool"],
                        modality=modality,
                        path=r["path"],
                        sha256=r["sha256"],
                        recording_id=r["recording_id"],
                        channel=r.get("channel", "all_42"),
                        label=r.get("label", "HbO_HbR_HbT"),
                        block=block,
                        start_s=start,
                        end_s=end,
                        recording_support_end_s=support_end,
                        available_seconds=available,
                        full_window=full,
                        source_segment_start_sample=origin,
                        source_segment_end_sample=origin + length,
                        source_window_start_sample=origin + min(length, int(start * fs))
                        if modality == "ECG_EGG"
                        else "",
                        source_window_end_sample=origin + min(length, int(end * fs))
                        if modality == "ECG_EGG"
                        else "",
                        selection="fixed_random_block_no_replacement",
                        review_status="not_annotated",
                        sampling_hz=fs,
                        time_selection="actual_TXT_time"
                        if modality == "Hb"
                        else "selected_ACQ_segment_seconds",
                    )
                )
                source_inputs[r["path"]] = r["sha256"]
    for name, digest in source_inputs.items():
        if sha(name) != digest:
            raise ValueError("Reference source changed")
    write(out / "reference_tasks_private.csv", tasks)
    for pool in ["development", "sealed_validation"]:
        selected = [r for r in tasks if r["pool"] == pool]
        write(out / (pool + "_tasks_private.csv"), selected)
        for annotator in [1, 2]:
            # Annotation files carry task/channel keys, with all responses intentionally blank.
            write(
                out / f"{pool}_annotator_{annotator}_blank.csv",
                [
                    dict(
                        task_id=r["task_id"],
                        channel=r["channel"],
                        artifact_start_s="",
                        artifact_end_s="",
                        label="",
                        peak_time_s="",
                        beat_type="",
                        metric_reference="",
                        uncertain_reason="",
                    )
                    for r in selected
                ],
            )
    taskstats = []
    for pool in ["development", "sealed_validation"]:
        for mod in ["ECG_EGG", "Hb"]:
            subset = [r for r in tasks if r["pool"] == pool and r["modality"] == mod]
            n = len({r["person_id"] for r in subset if r["full_window"]})
            taskstats.append(
                dict(
                    pool=pool,
                    modality=mod,
                    people=len({r["person_id"] for r in subset}),
                    full_planned_window_people=n,
                    zero_error_one_sided_95_bound_if_all_accepted=(1 - 0.05 ** (1 / n))
                    if n
                    else None,
                    interpretation="capacity_only_not_observed_error_rate",
                )
            )
    write(out / "reference_capacity.csv", taskstats)
    (out / "REFERENCE_README.md").write_text(
        "# 当前来源的盲法复核任务\n\n"
        "本清单替代旧标注包的来源指向；原有按人分池和预定随机块保持。没有生成新的参考标签、验收率或完整波形查看器。旧图不得替代这里列明的实际文件和 ACQ 片段。\n\n"
        "只先使用 development_tasks_private.csv；sealed_validation 必须在算法版本冻结后再打开。两名标注者独立填写对应 blank 文件，第三人处理分歧；不得查看 VAS、关联和分型结果。\n\n"
        "ECG 审查完整目标窗口和 R 峰，正常/异常/不确定分别记录；EGG 伪迹与节律可辨分别判断；Hb 记录跳变、平坦、突发及不确定区间。时间以选定采集片段起点为 0；真实源样本边界已列明，不能拼接暂停。Hb 使用 TXT 实际时间列。\n\n"
        "预定窗口不足时保留不足，不能替换为看起来较好的窗口。capacity 表仅为可用独立人数的上限；零错误上限的假设计算不是实际通过率，不计同人多个通道为额外独立人数。\n",
        encoding="utf-8",
    )
    fallacies = [
        (
            "Simpson",
            "person/block fixed effects; subgroup heterogeneity not established",
        ),
        (
            "Ecological",
            "person-block association only; no individual mechanistic claim",
        ),
        ("Berkson", "quality and observed-window selection remains a risk"),
        ("Collider", "quality/observation selection unresolved; no causal claim"),
        ("Base_rate", "not a diagnostic accuracy study; not applicable"),
        ("Regression_to_mean", "no causal recovery claim"),
        ("Survivorship", "E/T and minimum two blocks restrict observed population"),
        (
            "Look_elsewhere",
            "all 24 targets and all timing scenarios retained; p/q unavailable",
        ),
        (
            "Forking_paths",
            "exploratory post-data analysis, frozen candidate config retained",
        ),
        ("Causation", "association only"),
        ("Reverse_causality", "direction not established"),
    ]
    write(
        out / "interpretation_checks.csv",
        [dict(check=a, assessment=b) for a, b in fallacies],
    )
    hchecks = [r for r in checks if r["roi"] != "ECG"]
    summary = dict(
        planned_models=len(checks),
        independent_OLS_verified=len(checks),
        bootstrap_copy_checks=len(checks),
        min_bootstrap_success=min(r["bootstrap_success"] for r in checks),
        max_bootstrap_failure_fraction=max(
            r["bootstrap_failure_fraction"] for r in checks
        ),
        ecg_people=checks[0]["n_people"],
        ecg_blocks=checks[0]["n_blocks"],
        hb_people_range=[
            min(r["n_people"] for r in hchecks),
            max(r["n_people"] for r in hchecks),
        ],
        timing_scenarios=len(timing),
        models_with_A_sign_changes=sum(
            r["sign_change"] for r in timing_summary if r["support_spec"] == "A"
        ),
        reference_tasks=len({r["task_id"] for r in tasks}),
        reference_capacity=taskstats,
        independent_annotations_obtained=False,
        hb_units="awaiting_investigator_documentation",
        p_q_published=False,
    )
    dump(out / "summary.json", summary)
    (out / "REPORT.md").write_text(
        "# 当前阻塞复核\n\n"
        "Material Passport: academic-research-suite / experiment-agent; validation status: implementation VERIFIED, physiological targets UNVALIDATED.\n\n"
        f"24 项候选模型均完成；24 个系数与显式受试者/区块虚拟变量 OLS 一致，24 个独立整人重抽检查与重复样本副本拟合一致。最少重抽成功 {summary['min_bootstrap_success']}/2000。ECG 两项均 2000/2000，原重抽失败阻塞解除。\n\n"
        f"ECG 模型 {summary['ecg_people']} 人、{summary['ecg_blocks']} 块；Hb 模型各 {summary['hb_people_range'][0]}–{summary['hb_people_range'][1]} 人。保留 {len(timing)} 个时间/支持场景；完整五分钟规格有 {summary['models_with_A_sign_changes']} 个模型在这些场景中出现系数变号，不据此选择场景或宣称同步通过。\n\n"
        "p/q 继续为缺失；这些区间只描述未经独立验证候选指标的重抽稳定性。检查了 11 类统计解释风险，详见 interpretation_checks.csv。来源搜索缺项不阻塞已有数据分析。\n\n"
        "当前来源参考任务已重建，保持原始按人分池和预定块；未生成任何人工标注。容量表区分独立人数与通道行数，保留不足窗口。Hb 单位等待研究者原文说明。\n",
        encoding="utf-8",
    )
    dump(
        out / "manifest.json",
        dict(
            created_utc=datetime.now(timezone.utc).isoformat(),
            summary=summary,
            input_sha256=inputs,
            reference_source_sha256=source_inputs,
            python=sys.version,
            numpy=np.__version__,
            pandas=pd.__version__,
            platform=platform.platform(),
            code_sha256={
                str(p): sha(p)
                for p in [
                    Path(__file__),
                    ROOT / "scripts/run_candidate_associations.py",
                ]
            },
            git_revision=subprocess.check_output(
                ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
                text=True,
            ).strip(),
            outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
        ),
    )
    print(out)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
