"""Run frozen complete-case FPCA supplements with immutable provenance."""

import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RSCRIPT = "C:/Program Files/R/R-4.6.1/bin/Rscript.exe"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    config_path = ROOT / "config/fpca_followup_v1.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    assert (
        cfg["status"] == "frozen_provisional" and cfg["version"] == "fpca_followup_v1"
    )
    assert cfg["intervals"] == [[1, 20], [1, 10]] and cfg["components"] == [1, 2, 3, 4]
    prior = ROOT / cfg["input_run"]
    pm = prior / "run_manifest.json"
    prior_manifest = json.loads(pm.read_text(encoding="utf-8"))
    assert prior_manifest["status"] == "completed_provisional"
    for name, digest in prior_manifest["input_sha256"].items():
        assert sha(Path(name)) == digest, name
    for name, digest in prior_manifest["outputs_sha256"].items():
        assert sha(prior / name) == digest, name
    source_paths = [
        config_path,
        pm,
        Path(__file__),
        ROOT / "R/vas_models.R",
        ROOT / "R/fpca_followup.R",
        ROOT / "scripts/run_fpca_followup.R",
        ROOT / "scripts/test_fpca_followup.R",
        prior / "vas_long.csv",
    ]
    source_paths += [Path(p) for p in prior_manifest["input_sha256"]]
    hashes = {str(p.resolve()): sha(p) for p in source_paths}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "08_outputs" / f"fpca_followup_{stamp}_{uuid.uuid4().hex[:8]}"
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git
        + ["check-ignore", "--quiet", str(out / "complete_1_20_scores_private.csv")],
        cwd=ROOT,
        check=True,
    )
    out.mkdir(exist_ok=False)
    state = dict(
        status="running",
        configuration=cfg,
        created_utc=stamp,
        sources_sha256=hashes,
        python=platform.python_version(),
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    )

    def save():
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    def execute(command, log, env=None):
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=cfg["timeout_seconds"],
        )
        (out / log).write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"{log} exited {result.returncode}")

    save()
    try:
        temp = out / "test_temp"
        temp.mkdir()
        execute(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            "python_tests.log",
            dict(os.environ, TMP=str(temp), TEMP=str(temp)),
        )
        execute([RSCRIPT, "scripts/test_fpca_followup.R"], "r_tests.log")
        execute(
            [
                RSCRIPT,
                "scripts/run_fpca_followup.R",
                str(prior),
                str(out),
                str(cfg["bootstrap_replicates"]),
                str(cfg["cv_repeats"]),
                str(cfg["cv_folds"]),
                str(cfg["seed"]),
            ],
            "execution.log",
        )
        eig = read(out / "eigenvalues.csv")
        cv = read(out / "reconstruction_summary.csv")
        stability = read(out / "stability_summary.csv")
        redundancy = read(out / "redundancy.csv")
        checks = []
        for label, n_expected in [("complete_1_20", 57), ("complete_1_10", 207)]:
            ev = [r for r in eig if r["interval"] == label]
            assert len(ev) == 4 and all(int(r["n_subjects"]) == n_expected for r in ev)
            bs = read(out / f"{label}_bootstrap_status.csv")
            assert len(bs) == cfg["bootstrap_replicates"]
            folds = read(out / f"{label}_folds_private.csv")
            assert len(folds) == n_expected * cfg["cv_repeats"]
            assert len({(r["repeat_id"], r["subject_id"]) for r in folds}) == len(folds)
            errors = read(out / f"{label}_reconstruction_private.csv")
            assert len(errors) == len(folds) * 5
            grouped = {}
            for row in errors:
                grouped.setdefault((row["repeat_id"], row["subject_id"]), {})[
                    int(row["k"])
                ] = float(row["weighted_rmse"])
            assert all(
                set(v) == set(range(5))
                and all(v[k + 1] <= v[k] + 1e-10 for k in range(4))
                for v in grouped.values()
            )
            checks.append(
                dict(
                    interval=label,
                    n_subjects=n_expected,
                    bootstrap_attempts=len(bs),
                    bootstrap_success=sum(r["success"] == "TRUE" for r in bs),
                    cv_subject_repeat_count=len(folds),
                    nested_reconstruction_errors=True,
                )
            )
        report = [
            "# 完整轨迹FPCA稳定性与重复留出重建",
            "",
            "## Material Passport",
            "",
            "- Origin Skill: academic-research-suite / experiment-agent",
            "- Origin Mode: run + validate",
            "- Version: fpca_followup_v1",
            "- Verification: PROVISIONAL；工程核验完成，完整者选择未解决",
            "",
            "本轮使用既有v3长表，保留原VAS量纲与实际1–20/1–10分钟；仅纳入对应区间完整数值轨迹。E/T及原始零值不改写、不插补。与既有模型的特征值和解释率重算一致。受试者身份尚待核对，重抽和划分单位暂为候选受试者行。",
            "",
            "## 样本解释率与重建误差",
            "",
            "每区间500次整人bootstrap，另作10次5折受试者留出。每折仅以训练人估计均值和基函数；测试人的整个区间用于投影得分，因此是留出人群上的曲线压缩重建，不是未来预测、缺失评分预测或外部验证。0维是训练均值曲线基准。误差按梯形积分权重计算，再按人等权平均；重复划分均值范围只描述划分波动。",
            "",
            "|区间|完整人数|成分数|样本累计解释率|留出平均RMSE（VAS分）|10次划分均值范围|",
            "|---|---:|---:|---:|---:|---|",
        ]
        for row in cv:
            match = next(
                (
                    e
                    for e in eig
                    if e["interval"] == row["interval"] and e["k"] == row["k"]
                ),
                None,
            )
            fve = f"{100 * float(match['cumulative_fve']):.2f}%" if match else "0%"
            report.append(
                f"|{row['interval']}|{row['n_subjects']}|{row['k']}|{fve}|{float(row['mean_subject_rmse']):.4f}|{float(row['min_repeat_mean']):.4f}–{float(row['max_repeat_mean']):.4f}|"
            )
        report += [
            "",
            "## 子空间稳定性",
            "",
            "按特征值顺序取前k个成分，报告参考与重抽空间的最大主角度。0°表示空间重合；角度越大表示该维数的方向越不稳定。近重特征值下单轴可旋转，所以不能只依赖最优轴匹配后的相关。以下为经验bootstrap中位数与2.5–97.5百分位范围，并非经校准置信区间。",
            "",
            "|区间|前k维|成功/尝试|角度中位数|角度百分位范围|",
            "|---|---:|---:|---:|---|",
        ]
        for r in stability:
            if r["metric"] == "max_angle_deg":
                report.append(
                    f"|{r['interval']}|{r['k']}|{r['successful']}/{r['attempted']}|{float(r['median']):.2f}°|{float(r['lower']):.2f}–{float(r['upper']):.2f}°|"
                )
        report += [
            "",
            "## 同区间冗余",
            "",
            "Spearman相关仅描述；无p值或确认性多重检验。得分符号由展示约定确定，不赋予生理方向；AUC与均值来自相同评分，本身存在代数关联。首次观察峰时可含并列或边界最大值，不视为真实峰时。",
            "",
            "|区间|成分|指标|Spearman|",
            "|---|---:|---|---:|",
        ]
        for r in redundancy:
            report.append(
                f"|{r['interval']}|{r['k']}|{r['metric']}|{float(r['spearman']):.4f}|"
                if r["spearman"]
                else f"|{r['interval']}|{r['k']}|{r['metric']}|未定义|"
            )
        report += [
            "",
            "样本90%解释率交叉点仅作描述；增加成分可机械降低投影误差，不能凭重建误差持续下降决定最佳维数。两区间纳入人群不同，轴不能直接视作同一表型；未确认临床表型、维数或增量预测价值。本轮不是稀疏PACE，不能推广至全部216人完整20分钟的潜在轨迹。导数校准失败的限制继续保留。",
            "",
            "解释核查11/11：两区间分别报告（聚合反转）；不作群体到个体推断；完整者选择及碰撞风险保留；无诊断基础率主张；无极端分组改善主张；退出选择未解决；全部k与相关均报告；探索配置及既有结果知情性记录；不作因果或逆向因果解释。",
            "",
            "文件：[解释率](eigenvalues.csv)、[重建汇总](reconstruction_summary.csv)、[稳定性](stability_summary.csv)、[冗余](redundancy.csv)、[图](fpca_followup.png)、[核验](verification.json)、[来源与环境](run_manifest.json)。个体得分、折分配及逐人误差仅保存在本地私有输出。",
        ]
        (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        (out / "verification.json").write_text(
            json.dumps(checks, indent=2), encoding="utf-8"
        )
        for name, digest in hashes.items():
            assert sha(Path(name)) == digest, name
        for name, digest in prior_manifest["outputs_sha256"].items():
            assert sha(prior / name) == digest, name
        state.update(status="completed_provisional", checks=checks)
    except Exception as exc:
        state.update(status="failed", error=str(exc))
        raise
    finally:
        state["finished_utc"] = datetime.now(timezone.utc).isoformat()
        state["outputs_sha256"] = {
            str(p.relative_to(out)): sha(p)
            for p in out.rglob("*")
            if p.is_file() and p.name != "run_manifest.json"
        }
        save()
    print(out)


if __name__ == "__main__":
    main()
