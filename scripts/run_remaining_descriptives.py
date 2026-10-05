"""Finish prespecified descriptive VAS extensions without imputing records."""

import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from run_fpca_followup import ROOT, RSCRIPT, sha, read


def main():
    cp = ROOT / "config/remaining_analysis_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    prior = ROOT / cfg["input_run"]
    pm = prior / "run_manifest.json"
    old = json.loads(pm.read_text(encoding="utf-8"))
    for p, h in old["input_sha256"].items():
        assert sha(Path(p)) == h, p
    for p, h in old["outputs_sha256"].items():
        assert sha(prior / p) == h, p
    sources = [
        cp,
        pm,
        prior / "vas_long.csv",
        Path(__file__),
        ROOT / "scripts/run_fpca_followup.py",
        ROOT / "R/vas_models.R",
        ROOT / "R/remaining_descriptives.R",
        ROOT / "scripts/run_remaining_descriptives.R",
        ROOT / "scripts/test_remaining_descriptives.R",
    ] + [Path(p) for p in old["input_sha256"]]
    hashes = {str(p.resolve()): sha(p) for p in sources}
    out = (
        ROOT
        / "08_outputs"
        / (
            "remaining_descriptives_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "residual_metrics_private.csv")],
        check=True,
        cwd=ROOT,
    )
    out.mkdir()
    tmp = out / "test_temp"
    tmp.mkdir()
    state = dict(
        status="running",
        configuration=cfg,
        sources_sha256=hashes,
        python=platform.python_version(),
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], text=True, cwd=ROOT
        ).strip(),
    )

    def save():
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    save()
    print(out, flush=True)
    try:
        for cmd, name in [
            (
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                "python_tests.log",
            ),
            ([RSCRIPT, "scripts/test_remaining_descriptives.R"], "r_tests.log"),
            (
                [RSCRIPT, "scripts/run_remaining_descriptives.R", str(out)],
                "execution.log",
            ),
        ]:
            with (out / name).open("w", encoding="utf-8") as log:
                subprocess.run(
                    cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    cwd=ROOT,
                    env=dict(os.environ, TMP=str(tmp), TEMP=str(tmp)),
                    timeout=cfg["timeout_seconds"],
                    check=True,
                )
        rows = read(out / "summary.csv")
        corr = read(out / "burden_redundancy.csv")
        report = [
            "# 剩余VAS描述：个体去趋势敏感性、负担时序和功能深度",
            "",
            "## Material Passport",
            "",
            "- Origin Skill: academic-research-suite / experiment-agent",
            "- Origin Mode: run + validate",
            "- Version: remaining_analysis_v1",
            "- Verification: PROVISIONAL；描述性分析",
            "",
            "保留v3实测评分与实际分钟，不补基线零、不跨缺口、不填E/T。个体线性主模型、二次敏感性只拟合当前窗口内实测点，至少6点且3个相邻对。残余方差=SSE/(n-p)，残余MSSD仅用真实相邻对。去除特定低阶趋势不等于分离了真实波动与测量误差，也不证明残余不含趋势；不能作潜在不稳定性诊断或逐人AR分析。",
            "",
            "负担仅用完整区间：分段线性VAS的面积及时间一阶矩精确积分，重心=一阶矩/面积；1–20及1–10分钟的早晚分界分别为10.5和5.5分钟。分界内插仅用于已观测相邻段的积分，不生成新观测或补缺口。面积为零时重心/晚期比例未定义。",
            "",
            "## 汇总",
            "",
            "以下为逐人指标中位数及2000次整人重抽的探索性逐项百分位区间，未经覆盖校准；离散中位数可能给出零宽区间。不同区间人群不一致。残余方差/MSSD单位VAS²，面积VAS·分钟，时间重心分钟，晚期比例无量纲。",
            "",
            "|模块|区间终点|趋势次数|指标|人数|中位数|探索性范围|",
            "|---|---:|---:|---|---:|---:|---|",
        ]
        for r in rows:
            report.append(
                f"|{r['module']}|{r['end_min']}|{r['degree'] or '—'}|{r['metric']}|{r['n']}|{float(r['median']):.4f}|{float(r['lower']):.4f}–{float(r['upper']):.4f}|"
            )
        report += [
            "",
            "## 冗余关系",
            "",
            "Spearman只作描述，无p值；各指标来自同一曲线，不构成独立发现。观察峰可能并列或位于边界。",
            "",
            "|区间终点|指标|参照|人数|Spearman|",
            "|---|---|---|---:|---:|",
        ]
        for r in corr:
            report.append(
                f"|{r['end_min']}|{r['metric']}|{r['reference']}|{r['n']}|{float(r['spearman']):.4f}|"
            )
        report += [
            "",
            "## 功能深度图",
            "",
            "完整者在实际分钟网格上计算修正带深度，包含端点与并列值，按梯形时间权重汇总。中央集合按前ceil(n/2)名截点纳入所有并列者，所以人数可超过50%；包络不是置信带。最深曲线是实际观察曲线，仅展示中心，不排除低深度曲线，也不等同于逐点中位数。",
            "",
            "解释核查11/11：区间分开、无生态推断；完整者选择与碰撞风险保留；无诊断基础率主张；无极端组疗效解释；退出风险保留；全部指标/趋势方案披露；参数与既有结果知情性已记录；无因果或逆向因果主张。身份核对、导数校准、生理同步及状态阈值限制继续保留。",
            "",
            "[汇总](summary.csv)；[冗余](burden_redundancy.csv)；[功能深度图](functional_depth.png)；[包络](functional_envelopes.csv)；[来源/环境/测试](run_manifest.json)。逐人输出仅本地保存。",
        ]
        (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        for p, h in hashes.items():
            assert sha(Path(p)) == h, p
        for p, h in old["outputs_sha256"].items():
            assert sha(prior / p) == h, p
        state["status"] = "completed_provisional"
    except Exception as e:
        state.update(status="failed", error=str(e))
        raise
    finally:
        state["finished_utc"] = datetime.now(timezone.utc).isoformat()
        state["outputs_sha256"] = {
            str(p.relative_to(out)): sha(p)
            for p in out.rglob("*")
            if p.is_file() and p.name != "run_manifest.json"
        }
        save()


if __name__ == "__main__":
    main()
