"""Execute the frozen E/T follow-up without rewriting prior model results."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.analysis import locate_rscript, csv_rows
from capsaicin.cli import digest, write_json, write_csv
from capsaicin.contracts import ContractError, read_wide
from capsaicin.stopping import (
    audit_stopping,
    stopping_distribution,
    observed_bootstrap,
    bounded_means,
    area_bounds,
    grouped_observed,
)


def run(input_path, config_path, prior_run):
    start = datetime.now(timezone.utc)
    input_path = Path(input_path).resolve()
    config_path = Path(config_path).resolve()
    prior_run = Path(prior_run).resolve()
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    if cfg["status"] != "frozen_provisional" or cfg["version"] not in (
        "et_followup_v1",
        "et_followup_v2",
        "et_followup_v3",
    ):
        raise ContractError("Unsupported follow-up version")
    processed_E = cfg["version"] != "et_followup_v1"
    connected_E = cfg["version"] == "et_followup_v3"
    expected = json.loads(
        (ROOT / "config" / f"{cfg['version']}.json").read_text(encoding="utf-8")
    )
    if cfg != expected:
        raise ContractError(
            "Configuration differs from supported execution specification"
        )
    data_path = ROOT / cfg["data_config"]
    semantics_path = ROOT / cfg["semantics_config"]
    data_cfg = json.loads(data_path.read_text(encoding="utf-8"))
    semantics = json.loads(semantics_path.read_text(encoding="utf-8"))
    if (
        semantics["E"]["pain_free_duration_minutes"] != 2
        or semantics["T"]["meaning"] != "trial_discontinued"
    ):
        raise ContractError("Unexpected stopping definitions")
    if cfg["scale"] != [data_cfg["data"]["vas_min"], data_cfg["data"]["vas_max"]]:
        raise ContractError("Scale mismatch")
    prior_manifest = prior_run / "run_manifest.json"
    prior = json.loads(prior_manifest.read_text(encoding="utf-8"))
    if prior["status"] not in ("completed_provisional", "completed_with_model_issues"):
        raise ContractError("Prior model run not complete")
    if not all(digest(prior_run / p) == h for p, h in prior["outputs_sha256"].items()):
        raise ContractError("Prior output hash mismatch")
    if digest(input_path) != prior["input_sha256"].get(str(input_path)):
        raise ContractError(
            "Source differs from prior fit; rerun models before follow-up"
        )
    calibration = (
        ROOT
        / "02_quality_control/synthetic_calibration_20260916_v1/calibration_replicates.csv"
    )
    sources = [
        input_path,
        config_path,
        data_path,
        semantics_path,
        prior_manifest,
        calibration,
    ]
    hashes = {str(p): digest(p) for p in sources}
    codes = [
        Path(__file__),
        ROOT / "scripts/plot_et_followup.R",
        ROOT / "src/capsaicin/stopping.py",
        ROOT / "src/capsaicin/contracts.py",
        ROOT / "src/capsaicin/cli.py",
        ROOT / "src/capsaicin/analysis.py",
    ]
    if connected_E:
        codes.append(ROOT / "src/capsaicin/e_coding.py")
    code_hashes = {str(p.relative_to(ROOT)): digest(p) for p in codes}
    rows = read_wide(input_path, data_cfg)
    prior_long = csv_rows(prior_run / "vas_long.csv")
    keys = ["subject_id", "time_min", "status", "raw_token", "termination_code"]
    if len(rows) != len(prior_long) or any(
        any(str(a[k]) != b[k] for k in keys)
        or (a["vas"] is not None and a["vas"] != float(b["vas"]))
        or (a["vas"] is None and b["vas"] != "")
        for a, b in zip(rows, prior_long)
    ):
        raise ContractError("Parsed data differs from prior fit; no reuse allowed")
    out = (
        ROOT
        / "08_outputs"
        / f"et_followup_{start:%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:8]}"
    )
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git
        + [
            "check-ignore",
            "--quiet",
            str(out.relative_to(ROOT) / "stopping_audit_private.csv"),
        ],
        cwd=ROOT,
        check=True,
    )
    out.mkdir(parents=True, exist_ok=False)
    rscript = locate_rscript()
    manifest = dict(
        started_utc=start.isoformat(),
        status="running",
        synthetic=False,
        input_sha256=hashes,
        code_sha256=code_hashes,
        configuration_version=cfg["version"],
        git_commit=subprocess.run(
            git + ["rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
        git_status=subprocess.run(
            git + ["status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout,
        python=sys.version,
        platform=platform.platform(),
        seed=cfg["seed"],
        rscript=str(rscript),
        prior_model_run=str(prior_run),
        prior_output_hashes_verified=True,
        prior_model_input_equal=True,
        model_refit=False,
        scientific_readiness="provisional_stopping_record_alignment_and_identity_pending",
    )
    write_json(out / "run_manifest.json", manifest)
    try:
        write_json(out / "frozen_config.json", cfg)
        write_json(out / "marker_semantics.json", semantics)
        write_json(out / "data_config_snapshot.json", data_cfg)
        minutes = list(
            range(cfg["interval_minutes"][0], cfg["interval_minutes"][1] + 1)
        )
        audit = audit_stopping(rows, processed_E=processed_E)
        if processed_E:
            for item in audit:
                if item["E_recorded_support"] == "remaining_uncoded_zero_pair":
                    item["E_recorded_support"] = (
                        "additional_preceding_zero_pair_outside_authorized_eight_cells_retained"
                    )
        if connected_E:
            from capsaicin.e_coding import recode_connected_zeros

            _, remaining = recode_connected_zeros(csv_rows(input_path))
            if remaining:
                raise ContractError("Connected zero runs remain before E")
        distribution = stopping_distribution(audit, minutes)
        bootstrap_cfg = cfg["observed_curve"]
        print(
            json.dumps({"output": str(out), "stage": "subject_bootstrap_2000"}),
            flush=True,
        )
        curves = observed_bootstrap(
            rows,
            minutes,
            bootstrap_cfg["bootstrap_replicates"],
            cfg["seed"],
            bootstrap_cfg["level"],
            bootstrap_cfg["minimum_valid_fraction"],
        )
        bounds = bounded_means(rows, minutes, *cfg["scale"])
        area = area_bounds(bounds)
        write_csv(out / "stopping_audit_private.csv", audit)
        write_csv(out / "marker_distribution.csv", distribution)
        write_csv(out / "observed_curve_subject_bootstrap.csv", curves)
        write_csv(out / "cohort_mean_identification_bounds.csv", bounds)
        write_csv(out / "cohort_auc_identification_bounds.csv", [area])
        write_csv(
            out / "observed_by_eventual_marker.csv",
            grouped_observed(rows, audit, minutes),
        )
        summary = dict(
            candidate_rows=len(audit),
            n_observed=sum(r["n_observed"] for r in audit),
            eventual_markers=dict(Counter(r["eventual_marker"] for r in audit)),
            E_recorded_support=dict(
                Counter(
                    r["E_recorded_support"]
                    for r in audit
                    if r["eventual_marker"] == "E"
                )
            ),
            bootstrap_replicates=bootstrap_cfg["bootstrap_replicates"],
            minimum_bootstrap_valid=min(r["bootstrap_valid"] for r in curves),
            area_bounds=area,
            E_T_definitions_confirmed=True,
            individual_marker_alignment_verified=False,
        )
        write_json(out / "summary.json", summary)
        env = os.environ.copy()
        env.update(LC_ALL="C", LANG="C", LANGUAGE="en")
        command = [str(rscript), str(ROOT / "scripts/plot_et_followup.R"), str(out)]
        manifest["plot_command"] = command
        with (out / "plot_execution.log").open("w", encoding="utf-8") as log:
            process = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=cfg["timeout_seconds"],
                env=env,
            )
        manifest["plot_exit_code"] = process.returncode
        if process.returncode:
            raise RuntimeError("Plot process failed; inspect log")
        end = bounds[-1]
        end_curve = curves[-1]
        esupport = summary["E_recorded_support"]
        report = [
            "# E/T 停止机制与缺失范围分析",
            "",
            "## Material Passport",
            "",
            "- Origin Skill: academic-research-suite / experiment-agent",
            "- Origin Mode: run + validate",
            f"- Origin Date: {start.date()}",
            "- Verification Status: PROVISIONAL；定义已确认，逐例评分/停止时间及身份待核对",
            f"- Version Label: {cfg['version']}",
            "",
            f"本轮读取 {len(audit)} 行、{summary['n_observed']} 个实测评分，与前次模型输入逐格一致。E {summary['eventual_markers'].get('E', 0)} 行，T {summary['eventual_markers'].get('T', 0)} 行，无停止标记 {summary['eventual_markers'].get('none', 0)} 行。",
            "",
            "E 为连续两分钟无痛后停止；T 为中止，通常因刺激过强。文件名 T 仍为另一个采集序列，排除规则不变。",
            "停止机制与疼痛状态有关，晚期均值和完整者均是经过选择的观察样本。中止后是否采取干预尚未核实，因此不能将范围自动视为不改变照护条件下的反事实结局。",
            "",
            "## E 标记与记录支持",
            "",
            "|E 前两个计划分钟的实测记录|行数|",
            "|---|---|",
        ]
        labels = {
            "two_preceding_recorded_zeros": "两个相邻计划分钟均有数值零",
            "preceding_numeric_window_unavailable": "两个计划分钟的数值记录不足",
            "not_two_preceding_recorded_zeros_requires_review": "有两个数值记录，但不全为零；需核对编码对齐",
        }
        if processed_E:
            labels = {
                "existing_E_processed_no_preceding_zeros_required": "已有 E 为已处理编码，无需前置两格零",
                "additional_preceding_zero_pair_outside_authorized_eight_cells_retained": "编码起点前仍有双零（此次 8 格之外，保留，不判定需再编码）",
            }
        if connected_E:
            labels = {
                "existing_E_processed_no_preceding_zeros_required": "已有 E 为已处理编码，无需前置两格零"
            }
        for key, label in labels.items():
            report.append(f"|{label}|{esupport.get(key, 0)}|")
        if processed_E:
            report += [
                "",
                (
                    "本轮按用户继续修复要求，将已有 E 前剩余最大连续零段整体编码为 E，再改 8 格；与第一轮合计 16 格。再次应用规则不产生新修改。与 E 不相连的零值、缺口及 T 不改写。"
                    if connected_E
                    else "本次仅改指定 4 行原 E 前两格，共 8 格；不递归向前把更早零值也改为 E。已有 E 不要求前置双零，表中额外双零只作编码范围描述，不判定异常或要求追加处理。"
                ),
                "本轮数学范围仅使用统一编码后的分析表及 0–10 量表限制；所有被替换零值的原值仍保存于修改清单。该范围没有进一步利用被编码替换的信息或 E 停止规则，不是包含所有历史信息后的最窄范围。",
            ]
        report += [
            "",
            (
                "用户已明确 E 是处理后的编码；此前将 146 行列为需要核对前置零值的解释已撤回。授权修正的零值已在新副本改为 E，原值和字段保存在逐格修改清单；不将编码起点认定为实际停止时刻。"
                if processed_E
                else "该审计检查的是评分表能否直接支持用户说明的停止规则，不判定受试者报告或操作违反规则。E 可能替代了评分记录，标记与真实时间也可能不同；须查看原始记录，不能凭当前结果选择一种解释或自动补零。"
            ),
            "首次 E/T 列只用于记录位置分布，不是无痛起始时刻或已核实的停止时刻。累计比例使用全部候选行作分母；未将 T 当作独立删失估计疼痛缓解生存曲线。",
            "",
            "## 实测均值与缺失敏感性",
            "",
            f"第 20 分钟有 {end_curve['n_observed']} 行实测 VAS，均值 {end_curve['mean_observed']:.3f}，整人 bootstrap 95% 逐点区间 {end_curve['bootstrap_pointwise_lower']:.3f}–{end_curve['bootstrap_pointwise_upper']:.3f}。区间描述仍有观测者的均值，不消除停止带来的选择。",
            f"若全体候选行的未观测 VAS 只受 0–10 量表限制，第 20 分钟全队列均值的数学范围为 {end['cohort_mean_lower']:.3f}–{end['cohort_mean_upper']:.3f}。范围宽度中 E 缺测贡献 {end['width_due_to_E']:.3f}，T 缺测贡献 {end['width_due_to_T']:.3f}，其他缺测贡献 {end['width_due_to_other_missing']:.3f}。",
            f"1–20 分钟全队列平均梯形面积的数学范围为 {area['candidate_mean_auc_lower']:.3f}–{area['candidate_mean_auc_upper']:.3f} VAS·分钟。未添加第 0 分钟。",
            "",
            "这些范围是固定样本、离散评分网格上的代数极值，不是置信区间，也不是插补后重新拟合的结果。每个未知格只参与上下界计算，未生成或改写个体评分。E 后持续零与 T 后持续高值均未作为科学假设采用。",
            "bootstrap 每次抽取完整候选行，保留其缺测模式，输出每分钟有效与无观测重采样次数；未按最终停止类型构建预测特征。按最终 E/T 分组的曲线仅作回顾性描述。",
            "",
            "## 既有模型及后续条件",
            "",
            f"既有模型输出与输入摘要核验通过，未重复拟合：[前次模型报告]({(prior_run / 'REPORT.md').as_posix()})。旧报告中未确认的 E/T 语义由本报告替代解释，历史文件保留。",
            "此前合成弯曲轨迹伴退出时，GAMM 导数 95% 同时带覆盖仅 75%（40 次）；该校准问题仍存在，本轮 bootstrap 的实测均值区间不是导数区间的修复。",
            "稀疏 PACE、生理与 Markov/耦合仍未完成；本轮未声称全方案就绪。下一步需逐例核对停止标记与评分的对应、身份及访视；数值缺失情景、事件时间结局和统计校准应另建版本后运行。",
            "",
            "## 文件入口",
            "",
            "- [停止分布与缺失范围图](stopping_and_missingness.png)",
            "- [按最终停止标记分组的实测曲线](observed_by_marker.png)",
            "- [逐例核对表（私有）](stopping_audit_private.csv)",
            "- [逐分钟实测均值与 bootstrap 区间](observed_curve_subject_bootstrap.csv)",
            "- [全队列均值识别范围](cohort_mean_identification_bounds.csv)",
            "- [来源、环境与校验记录](run_manifest.json)",
        ]
        (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        if any(digest(Path(p)) != h for p, h in hashes.items()):
            raise RuntimeError("Input changed during execution")
        if any(digest(ROOT / p) != h for p, h in code_hashes.items()):
            raise RuntimeError("Code changed during execution")
        if not all(
            digest(prior_run / p) == h for p, h in prior["outputs_sha256"].items()
        ):
            raise RuntimeError("Prior outputs changed during execution")
        manifest.update(
            status="completed_provisional",
            exit_code=0,
            input_unchanged=True,
            prior_outputs_unchanged=True,
        )
    except BaseException as exc:
        manifest.update(status="failed", exit_code=1, error=str(exc))
        raise
    finally:
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["outputs_sha256"] = {
            p.name: digest(p)
            for p in out.iterdir()
            if p.is_file() and p.name != "run_manifest.json"
        }
        write_json(out / "run_manifest.json", manifest)
    print(
        json.dumps({"output": str(out), "summary": summary}, ensure_ascii=False),
        flush=True,
    )
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--config", default=str(ROOT / "config/et_followup_v1.json"))
    parser.add_argument("--prior-run", required=True)
    args = parser.parse_args()
    run(args.input, args.config, args.prior_run)
