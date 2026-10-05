"""Auditable provisional VAS execution; existing scientific gates stay explicit."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import uuid

from .cli import ROOT, digest, git_revision, resolve, write_csv, write_json
from .contracts import ContractError, read_wide
from .qc import subject_descriptives, time_counts
from .data_locations import execution_config, relocation_evidence


def validate_execution_config(config):
    if config.get("status") != "frozen_provisional" or not config.get(
        "execution_version"
    ):
        raise ContractError(
            "Execution needs a versioned frozen_provisional configuration"
        )
    if not config.get("execution", {}).get("allow_provisional"):
        raise ContractError("Provisional execution must be explicit")
    if config["estimand"]["analysis_interval_min"] != [1, 20]:
        raise ContractError("This model runner implements minutes 1-20 only")
    if config["data"]["expected_minutes"] != list(range(1, 21)):
        raise ContractError("Scheduled minutes must match the estimand")
    if (config["data"]["vas_min"], config["data"]["vas_max"]) != (0, 10):
        raise ContractError("This model runner requires the documented 0-10 scale")
    if config["fpca"]["engine"] != "weighted_grid_PCA_complete_cases_only":
        raise ContractError(
            "Unsupported FPCA engine; never substitute estimators silently"
        )
    for key in ("bootstrap_subjects", "coefficient_draws", "k_candidate"):
        if type(config["gamm"][key]) is not int or config["gamm"][key] < 1:
            raise ContractError(f"Invalid GAMM parameter: {key}")
    if (
        config["gamm"]["bootstrap_subjects"] < 20
        or config["gamm"]["coefficient_draws"] < 100
    ):
        raise ContractError("Insufficient bootstrap/draw count")
    if config["fpca"]["subject_bootstrap"] < 20:
        raise ContractError("Insufficient FPCA bootstrap count")
    for section in ("physiology", "markov", "coupling"):
        if config[section]["enabled"]:
            raise ContractError(f"{section} is not implemented in this runner")
    if config["inference"]["prediction_enabled"]:
        raise ContractError("Prediction is not implemented")
    if (
        config["fpca"]["max_components_candidate"] != 4
        or config["gamm"]["simultaneous_level"] != 0.95
    ):
        raise ContractError("Runner implements four FPCA axes and 95% bands")
    if (
        config["execution"]["common_interval_min"]
        != config["fpca"]["common_interval_min"]
    ):
        raise ContractError("Inconsistent common intervals")


def observed_summaries(rows):
    """AUC is sum over observed adjacent intervals; unequal coverage stays visible."""
    groups = defaultdict(list)
    for row in rows:
        groups[row["subject_id"]].append(row)
    result = subject_descriptives(rows)
    for summary in result:
        z = sorted(
            (r for r in groups[summary["subject_id"]] if r["status"] == "observed"),
            key=lambda r: r["time_min"],
        )
        pairs = [(a, b) for a, b in zip(z, z[1:]) if b["time_min"] - a["time_min"] == 1]
        peak = max((r["vas"] for r in z), default=None)
        summary.update(
            observed_adjacent_auc=sum((a["vas"] + b["vas"]) / 2 for a, b in pairs)
            if pairs
            else None,
            auc_covered_minutes=len(pairs),
            peak_observed_vas=peak,
            first_observed_peak_min=next(
                (r["time_min"] for r in z if r["vas"] == peak), None
            ),
            peak_at_last_observation=bool(z and z[-1]["vas"] == peak),
            complete_1_20=len(z) == 20,
        )
    return result


def locate_rscript(explicit=None):
    if explicit:
        path = Path(explicit)
    else:
        found = shutil.which("Rscript")
        candidates = sorted(Path("C:/Program Files/R").glob("R-*/bin/Rscript.exe"))
        path = Path(found) if found else (candidates[-1] if candidates else None)
    if path is None or not path.is_file():
        raise ContractError(
            "Rscript missing; install R with mgcv/nlme or pass --rscript"
        )
    return path


def csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def run_analysis(input_path, config_path, output=None, rscript=None, evidence_paths=()):
    start = datetime.now(timezone.utc)
    input_path, config_path = resolve(input_path), execution_config(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_execution_config(config)
    r = locate_rscript(rscript)
    sources = (
        [input_path, config_path]
        + [resolve(p) for p in evidence_paths]
        + relocation_evidence()
    )
    semantics = None
    if config.get("marker_semantics_config"):
        semantic_path = resolve(config["marker_semantics_config"])
        sources.append(semantic_path)
        semantics = json.loads(semantic_path.read_text(encoding="utf-8"))
    if config.get("coding_rule_config"):
        sources.append(resolve(config["coding_rule_config"]))
    hashes = {str(p): digest(p) for p in sources}
    rows = read_wide(input_path, config)
    name = f"provisional_vas_{start:%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:8]}"
    out = resolve(output) if output else ROOT / "08_outputs" / name
    # Individual records must remain excluded from Git, even for explicit destinations.
    relative = out.resolve().relative_to(ROOT.resolve())
    git_command = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    probe = subprocess.run(
        git_command + ["check-ignore", "--quiet", str(relative / "vas_long.csv")],
        cwd=ROOT,
    )
    if probe.returncode != 0:
        raise ContractError("Output must be a Git-ignored private run directory")
    out.mkdir(parents=True, exist_ok=False)
    code_paths = (
        [ROOT / "run.py"]
        + list((ROOT / "src").rglob("*.py"))
        + [ROOT / "R/vas_models.R", ROOT / "scripts/run_vas_models.R"]
    )
    manifest = {
        "started_utc": start.isoformat(),
        "status": "running",
        "synthetic": config["execution"]["synthetic"],
        "scientific_readiness": "provisional_identity_and_semantics_pending",
        "git_commit": subprocess.run(
            git_command + ["rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
        "code_sha256": {str(p.relative_to(ROOT)): digest(p) for p in code_paths},
        "input_sha256": hashes,
        "config_version": config["execution_version"],
        "python": sys.version,
        "platform": platform.platform(),
        "seed": config["seed"],
        "rscript": str(r),
        "git_status": subprocess.run(
            git_command + ["status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout,
        "disabled_modules": config["execution"]["disabled_reasons"],
    }
    write_json(out / "run_manifest.json", manifest)
    try:
        write_json(out / "frozen_config.json", config)
        if semantics:
            write_json(out / "marker_semantics.json", semantics)
        write_csv(out / "vas_long.csv", rows)
        counts = time_counts(rows)
        write_csv(out / "time_counts.csv", counts)
        summaries = observed_summaries(rows)
        write_csv(out / "subject_descriptives_private.csv", summaries)
        events = [
            {
                "subject_id": x["subject_id"],
                "first_marker_min": x["first_marker_min"],
                "termination_code": x["termination_code"],
                "verified_event_time_min": None,
                "event_semantics": semantics[x["termination_code"]]["meaning"]
                if semantics
                else "unverified",
            }
            for x in summaries
            if x["termination_code"]
        ]
        if events:
            write_csv(out / "termination_markers_private.csv", events)
        else:
            (out / "termination_markers_private.csv").write_text(
                "subject_id,first_marker_min,termination_code,verified_event_time_min,event_semantics\n",
                encoding="utf-8",
            )
        minute_means = []
        for t in range(1, 21):
            vals = [
                x["vas"]
                for x in rows
                if x["time_min"] == t and x["status"] == "observed"
            ]
            minute_means.append(
                dict(
                    time_min=t,
                    n_observed=len(vals),
                    mean=sum(vals) / len(vals) if vals else None,
                )
            )
        write_csv(out / "observed_minute_means.csv", minute_means)
        overview = {
            "candidate_rows": len(summaries),
            "observed_values": sum(x["n_observed"] for x in summaries),
            "complete_1_20": sum(x["complete_1_20"] for x in summaries),
            "all_missing": sum(x["n_observed"] == 0 for x in summaries),
            "termination_subjects": dict(
                Counter(x["termination_code"] or "none" for x in summaries)
            ),
        }
        write_json(out / "data_overview.json", overview)
        command = [
            str(r),
            str(ROOT / "scripts/run_vas_models.R"),
            str(ROOT),
            str(out),
            str(config["seed"]),
            str(config["gamm"]["bootstrap_subjects"]),
            str(config["fpca"]["subject_bootstrap"]),
            str(config["gamm"]["coefficient_draws"]),
            str(config["gamm"]["k_candidate"]),
            ",".join(map(str, config["gamm"]["k_sensitivity"])),
            *map(str, config["execution"]["common_interval_min"]),
        ]
        manifest["command"] = command
        write_json(out / "run_manifest.json", manifest)
        env = os.environ.copy()
        env.update(LC_ALL="C", LANG="C", LANGUAGE="en")
        print(json.dumps({"output": str(out), "status": "running"}), flush=True)
        with (out / "model_execution.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env
            )
            deadline = time.monotonic() + config["execution"]["timeout_seconds"]
            while process.poll() is None:
                if time.monotonic() > deadline:
                    print("Hard timeout reached; terminating model process", flush=True)
                    process.kill()
                    process.wait()
                    raise TimeoutError("Model hard timeout")
                write_json(
                    out / "progress.json",
                    {
                        "pid": process.pid,
                        "status": "running",
                        "updated_utc": datetime.now(timezone.utc).isoformat(),
                    },
                )
                time.sleep(2)
        manifest["model_exit_code"] = process.returncode
        if process.returncode:
            raise RuntimeError(
                f"R model execution failed ({process.returncode}); see model_execution.log"
            )
        statuses = csv_rows(out / "model_status.csv")
        report = [
            "# VAS 暂定分析结果",
            "",
            "## Material Passport",
            "",
            "- Origin Skill: academic-research-suite / experiment-agent",
            "- Origin Mode: run + validation",
            f"- Origin Date: {start.date()}",
            "- Verification Status: PROVISIONAL；身份及逐例停止时间待核对；非最终推断"
            if semantics
            else "- Verification Status: PROVISIONAL；受试者身份及 E/T 语义待核对；非最终推断",
            f"- Version Label: {config['execution_version']}",
            "",
            f"当前候选表 {overview['candidate_rows']} 行，实测评分 {overview['observed_values']} 个；完整 1–20 分钟轨迹 {overview['complete_1_20']} 行。",
            f"E/T 标记涉及行数：{overview['termination_subjects']}。标记列位置不等于已核实的实际终止时刻。",
            "本次以现有 CRF 的 0–10 量纲和 1–20 分钟为范围。E/T、缺测和实际分钟原样保留；无基线零填充或跨缺口相邻差。",
            "",
            "|模块|运行状态|说明|",
            "|---|---|---|",
        ]
        for z in statuses:
            report.append(f"|{z['module']}|{z['status']}|{z['detail']}|")
        if semantics:
            report.extend(
                [
                    "",
                    "E 表示连续两分钟无痛后的已处理编码，不要求 E 前仍保留两个零值。按版本化规则在分析副本修正未处理的零值，具体字段和原值见修改清单；T 是中止，通常因刺激过强。首次编码 E 的位置不直接等于真实停止时刻。",
                ]
            )
        report.extend(
            [
                "",
                "本次系数同时带以拟合模型为条件；整人 bootstrap 用于检查平滑及相关结构重估后的稳定性，其百分位区间是逐点区间。工程验证不等于统计覆盖率已经校准。",
                "完整者功能 PCA 仅反映该完整观察子集；不能取代稀疏 FPCA，也不能消除选择偏倚。留出受试者的完整曲线用于得分与重建，不是前瞻预测。",
                "原始 SD/MSSD 含时间趋势及评分误差；群体 GAMM 的条件残差不作为个体残余不稳定性指标。",
                "",
                "## 未运行模块与具体条件",
                "",
                "|模块|原因|",
                "|---|---|",
            ]
        )
        for key, value in manifest["disabled_modules"].items():
            report.append(f"|{key}|{value}|")
        report.extend(
            [
                "",
                "## 核对后重跑",
                "",
                "保留本次目录，修改配置为新版本，再用相同 analyze 入口运行。先核对重复身份/访视、VAS 对应关系、E/T 定义及事件时间；生理关联还需窗口、单位、同步与质量审计。",
                "输入、配置和实际代码摘要见 run_manifest.json；软件环境见 sessionInfo.txt。个体记录均仅保存在本地 Git 忽略目录。",
            ]
        )
        (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        changed = [str(p) for p in sources if digest(p) != hashes[str(p)]]
        if changed:
            raise RuntimeError("Input/config/evidence changed during run")
        if any(digest(ROOT / p) != h for p, h in manifest["code_sha256"].items()):
            raise RuntimeError("Execution code changed during run")
        manifest["status"] = (
            "completed_provisional"
            if all(z["status"] == "completed_provisional" for z in statuses)
            else "completed_with_model_issues"
        )
        manifest["model_status"] = statuses
        manifest["input_unchanged"] = True
        write_json(
            out / "progress.json",
            {
                "status": manifest["status"],
                "updated_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
    except BaseException as exc:
        manifest.update(status="failed", error=str(exc))
        raise
    finally:
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["outputs_sha256"] = {
            p.name: digest(p)
            for p in out.iterdir()
            if p.is_file() and p.name != "run_manifest.json"
        }
        write_json(out / "run_manifest.json", manifest)
    print(json.dumps({"output": str(out), "status": manifest["status"]}), flush=True)
    return 0 if manifest["status"] == "completed_provisional" else 2
