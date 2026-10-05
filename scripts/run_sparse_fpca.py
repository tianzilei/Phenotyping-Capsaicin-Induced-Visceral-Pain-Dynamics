"""Provenance-preserving sparse FPCA simulation and exploratory execution."""

import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from run_fpca_followup import sha, read, ROOT, RSCRIPT


def main():
    cp = ROOT / "config/sparse_fpca_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    assert cfg["status"] == "frozen_exploratory"
    prior = ROOT / cfg["input_run"]
    pm = prior / "run_manifest.json"
    old = json.loads(pm.read_text(encoding="utf-8"))
    assert old["status"] == "completed_provisional"
    for name, digest in old["input_sha256"].items():
        assert sha(Path(name)) == digest, name
    for name, digest in old["outputs_sha256"].items():
        assert sha(prior / name) == digest, name
    sources = [
        cp,
        pm,
        prior / "vas_long.csv",
        Path(__file__),
        ROOT / "scripts/run_fpca_followup.py",
        ROOT / "scripts/run_sparse_fpca.R",
        ROOT / "scripts/test_sparse_fpca.R",
        ROOT / "R/sparse_fpca.R",
        ROOT / "scripts/install_sparse_fpca.R",
    ]
    sources += [Path(p) for p in old["input_sha256"]]
    sources += [
        p for p in (ROOT / "renv/library/sparse-fpca").rglob("*") if p.is_file()
    ]
    hashes = {str(p.resolve()): sha(p) for p in sources}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "08_outputs" / f"sparse_fpca_{stamp}_{uuid.uuid4().hex[:8]}"
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "sparse_1_20_scores_private.csv")],
        cwd=ROOT,
        check=True,
    )
    out.mkdir(exist_ok=False)
    temp = out / "test_temp"
    temp.mkdir()
    state = dict(
        status="running",
        configuration=cfg,
        created_utc=stamp,
        python=platform.python_version(),
        sources_sha256=hashes,
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    )

    def save():
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    def run(cmd, name):
        with (out / name).open("w", encoding="utf-8") as log:
            subprocess.run(
                cmd,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=dict(os.environ, TMP=str(temp), TEMP=str(temp)),
                timeout=cfg["timeout_seconds"],
                check=True,
            )

    save()
    print(out, flush=True)
    try:
        run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            "python_tests.log",
        )
        run([RSCRIPT, "scripts/test_sparse_fpca.R"], "r_tests.log")
        run([RSCRIPT, "scripts/run_sparse_fpca.R", str(out)], "execution.log")
        sim = read(out / "simulation_results.csv")
        eig = read(out / "eigenvalues.csv")
        st = read(out / "stability_summary.csv")
        sens = read(out / "bandwidth_sensitivity.csv")
        assert len(sim) == 60 and all(r["success"] == "TRUE" for r in sim)
        report = [
            "# 不平衡轨迹稀疏FPCA探索分析",
            "",
            "## Material Passport",
            "",
            "- Origin Skill: academic-research-suite / experiment-agent",
            "- Origin Mode: run + validate",
            "- Version: sparse_fpca_v1",
            "- Verification: PROVISIONAL；工程检查完成，观察选择假设未验证",
            "",
            "使用fdapace 0.6.0的Sparse工作模型，均值/协方差固定带宽2/3分钟，原VAS尺度，CE得分。模型通过平滑与协方差假设利用不完整轨迹；它不能识别E/T信息性退出后的全队列真实轨迹。E/T和零值不改写，未导出停止后个体补值。模型内部的得分估计不等于实测评分。",
            "",
            "## 合成工程验证",
            "",
            "每情景20份216人合成数据，已知两维信号。均值误差与前二维主角度仅描述，不作覆盖校准；所有拟合有限、得分维度及拟合协方差半正定检查通过，才进入真实数据。噪声方差是工作模型估计，不等同于已验证测量误差。",
            "",
            "|情景|成功/尝试|平均均值RMSE|平均前二维角度|",
            "|---|---:|---:|---:|",
        ]
        for scenario in cfg["simulation"]["scenarios"]:
            rows = [r for r in sim if r["scenario"] == scenario]
            report.append(
                f"|{scenario}|{sum(r['success'] == 'TRUE' for r in rows)}/{len(rows)}|{sum(float(r['mean_rmse']) for r in rows) / len(rows):.4f}|{sum(float(r['leading2_angle_deg']) for r in rows) / len(rows):.2f}°|"
            )
        report += [
            "",
            "## 真实数据工作模型",
            "",
            "固定报告前四维，解释率分母由平滑协方差全部正特征值计算；不将四维之和强制归一为100%。包在固定四维模式下内部将FVEthreshold设为1，实际选项已保存；本报告未使用其自动维数选择。平滑潜在协方差与完整者原评分PCA的方差对象、人群及噪声处理不同，解释率不能直接比较为性能提升。51点内部积分网格不代表采集了亚分钟数据。",
            "",
            "|区间|候选人数|数值评分数|维数|累计解释率|噪声方差估计|",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for r in eig:
            report.append(
                f"|{r['interval']}|{r['n_subjects']}|{r['n_observations']}|{r['k']}|{100 * float(r['cumulative_fve']):.2f}%|{float(r['sigma2']):.4f}|"
            )
        report += [
            "",
            "## 整人重抽稳定性",
            "",
            "每区间100次整人重抽，带宽固定，重新估计均值/协方差/基函数；按特征值顺序比较前k维，加权QR正交化后计算主角度。经验百分位只描述当前工作模型下的重抽波动，不是置信带，不能纳入未识别的退出偏倚。成功率门槛95%仅工程门槛。",
            "",
            "|区间|维数|成功/尝试|成功率门槛|角度中位数|2.5–97.5百分位|",
            "|---|---:|---:|---|---:|---|",
        ]
        for r in st:
            report.append(
                f"|{r['interval']}|{r['k']}|{r['successful']}/{r['attempted']}|{r['success_gate']}|{float(r['median']):.2f}°|{float(r['lower']):.2f}–{float(r['upper']):.2f}°|"
            )
        report += [
            "",
            "## 带宽敏感性",
            "",
            "带宽是运行前确定的工程尺度；未按真实结果寻优，三个尺度全部报告。此处相对主配置的角度反映方法敏感性，不是抽样误差。",
            "",
            "|区间|均值/协方差带宽（分钟）|维数|成功|与主配置角度|累计解释率|",
            "|---|---|---:|---|---:|---:|",
        ]
        for r in sens:
            angle = (
                f"{float(r['angle_from_primary']):.2f}°"
                if r["angle_from_primary"]
                else "未定义"
            )
            fve = (
                f"{float(r['cumulative_fve']) * 100:.2f}%"
                if r["cumulative_fve"]
                else "未定义"
            )
            report.append(
                f"|{r['interval']}|{r['bw_mean']}/{r['bw_covariance']}|{r['k']}|{r['success']}|{angle}|{fve}|"
            )
        report += [
            "",
            "逐时间对的共同观察人数保存在支持表；晚期协方差由仍有评分者支持，并非全216人的完整观测。CE得分随观察时长及工作模型假设变化，不能直接当作已经验证的表型，也不与未核对生理映射开展关联。未进行预测验证、临床维数确认或因果推断。导数校准失败限制继续保留。",
            "",
            "软件警告保留：1–10分钟每个相邻评分间隔1分钟，占总跨度9分钟的11.1%，触发包的10%时间间隔提示；这是当前离散采样网格的限制，不能把内部51点视为更密集实测。图中黑线为平滑工作均值，蓝点为逐分钟实测均值。",
            "",
            "解释核查11/11：区间分开；不作群体到个体推断；选择及碰撞风险保留；无诊断基础率主张；无极端分组改善主张；退出选择未解决；报告全部配置；参数提前冻结且追加探索已披露；无因果或逆向因果主张。",
            "",
            "[模拟结果](simulation_results.csv)；[解释率](eigenvalues.csv)；[稳定性](stability_summary.csv)；[敏感性](bandwidth_sensitivity.csv)；[共同观察支持](joint_observation_support.csv)；[图](sparse_fpca.png)；[全部警告](warnings.csv)；[软件帮助](fdapace_help.txt)；[来源与环境](run_manifest.json)。",
        ]
        (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        for name, digest in hashes.items():
            assert sha(Path(name)) == digest, name
        for name, digest in old["outputs_sha256"].items():
            assert sha(prior / name) == digest, name
        state["status"] = (
            "completed_exploratory"
            if all(r["success_gate"] == "TRUE" for r in st)
            else "completed_with_stability_failures"
        )
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
    print(state["status"])


if __name__ == "__main__":
    main()
