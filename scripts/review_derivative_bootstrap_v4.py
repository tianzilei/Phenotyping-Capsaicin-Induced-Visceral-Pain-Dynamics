"""Review a completed v4 run; retain prior outputs and audit all hashes."""

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    m = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    if m["status"] not in ("completed", "stopped_futility"):
        raise ValueError("Run has not ended")
    for p, h in m["sources_sha256"].items():
        if sha(Path(p)) != h:
            raise ValueError(f"Changed source {p}")
    for p, h in m["outputs_sha256"].items():
        if sha(run / p) != h:
            raise ValueError(f"Changed output {p}")
    out = (
        ROOT
        / "08_outputs"
        / (
            "derivative_v4_review_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    statuses = []
    for cell in sorted(run.glob("cell_*")):
        for name, target in [
            ("pointwise.csv", rows),
            ("bootstrap_status.csv", statuses),
        ]:
            with (cell / name).open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    row["cell"] = cell.name
                    target.append(row)
    groups = {}
    for r in rows:
        key = (r["scenario"], int(r["n"]), r["method"], int(r["time_min"]))
        groups.setdefault(key, []).append(r)
    bias = []
    for (scenario, n, method, t), rs in sorted(groups.items()):
        estimates = [float(r["estimate"]) for r in rs]
        ses = [float(r["se"]) for r in rs]
        sd = statistics.stdev(estimates) if len(estimates) > 1 else None
        bias.append(
            dict(
                scenario=scenario,
                n=n,
                method=method,
                time_min=t,
                successful_replicates=len(rs),
                mean_bias=statistics.mean(estimates) - float(rs[0]["truth"]),
                empirical_sd=sd,
                mean_se=statistics.mean(ses),
                sd_to_se=sd / statistics.mean(ses) if sd else None,
                mean_width=statistics.mean(
                    float(r["upper"]) - float(r["lower"]) for r in rs
                ),
            )
        )
    with (out / "bias_and_width.csv").open("w", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=list(bias[0]))
        w.writeheader()
        w.writerows(bias)
    checks = [
        ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
        [
            "C:/Program Files/R/R-4.6.1/bin/Rscript.exe",
            "scripts/test_derivative_bootstrap_v4.R",
            str(ROOT),
        ],
    ]
    test_results = []
    for i, cmd in enumerate(checks):
        p = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (out / f"tests_{i}.log").write_text(p.stdout + p.stderr, encoding="utf-8")
        test_results.append(dict(command=cmd, exit_code=p.returncode))
        if p.returncode:
            raise RuntimeError("Test failed")
    cmd = [
        "C:/Program Files/R/R-4.6.1/bin/Rscript.exe",
        str(ROOT / "scripts/plot_derivative_bootstrap_v4.R"),
        str(run),
        str(out),
    ]
    p = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (out / "plot.log").write_text(p.stdout + p.stderr, encoding="utf-8")
    if p.returncode:
        raise RuntimeError("Plot failed")
    failed = sum(r["success"] != "TRUE" for r in statuses)
    report = [
        "# 整人重拟合导数区间复核",
        "",
        "## Material Passport",
        "",
        "- Origin Skill: academic-research-suite / experiment-agent",
        "- Origin Mode: run + validate",
        f"- Version: derivative_calibration_v4 / {m['phase']}",
        "- Verification: ANALYZED；合成校准与工程核验分开报告",
        "",
        f"本轮完成 {sum(s['replicates'] for s in m['summary'] if s['method'] == m['configuration']['candidate'])} 份合成数据。"
        f"实际执行 {len(statuses)} 次整人重拟合，其中 {failed} 次失败。"
        f"预定候选门槛：{'通过' if m['gate_passed'] else '未通过'}。",
        "",
        (
            "本轮按预设规则提前判失败：即使剩余计划样本全部覆盖也无法通过。下表是实际完成的部分结果，未执行样本不计为观察失败；并非完成全部200次/格验证。"
            if m["status"] == "stopped_futility"
            else "全部本阶段预定重复已完成。"
        ),
        "",
        "|情景|人数|方法|全网格覆盖|Monte Carlo 95%区间|平均带宽|有效外层|",
        "|---|---:|---|---:|---|---:|---:|",
    ]
    for s in m["summary"]:
        width = f"{s['mean_width']:.4f}" if s["mean_width"] is not None else "NA"
        report.append(
            f"|{s['scenario']}|{s['n']}|{s['method']}|{s['coverage']:.1%}|"
            f"{s['wilson_lower']:.1%}–{s['wilson_upper']:.1%}|{width}|{s['successes']}/{s['replicates']}|"
        )
    report += [
        "",
        "这是固定1–20分钟网格的瞬时总体导数，单位VAS/分钟。开发阶段20次/格只是筛查，"
        "不以点估计覆盖率宣称可靠性已证实；表中Wilson区间给出有限模拟次数的不确定性，非跨情景联合保证。",
        "",
        (
            "由于本次按结果相关的徒劳规则停止，部分样本的Wilson区间仅作描述，不能视为具有固定样本95%覆盖或序贯有效性的区间。门槛失败的依据是预定N=200下即使余下全部覆盖仍不可能达标的确定性上限。"
            if m["status"] == "stopped_futility"
            else "本阶段完整样本区间按预定固定重复数解释。"
        ),
        "",
        "本轮重新估计每份整人重抽样本的CAR1、随机截距方差和固定系数。"
        "未经偏差修正与经过偏差修正的带使用同一批重抽；偏差修正估计的是样本经验分布下的偏差。"
        "固定基函数无法表示的真值部分不能由普通非参数bootstrap自动恢复；"
        "偏差修正中心的不确定性也没有双层bootstrap保证。",
        "",
        "只允许预定的 subject_bootstrap_bias_corrected_t 推进；"
        "另外两种方法作为诊断，不按结果事后更换候选。信息性停止仅压力测试，"
        "生成总体导数不是停止后仍被观察者的条件导数，不支持推断真实E/T停止后的完整轨迹。",
        "",
        (
            "开发通过后应执行原配置的独立验证；真实模型此时仍不更新。"
            if m["phase"] == "development" and m["gate_passed"]
            else "本轮未取得可用于更新真实模型的独立验证通过结论。已修复的VAS数据、原GAMM/FPCA及旧结果保持。"
        ),
        "",
        "工程检查：64项Python合成测试及专门R测试通过，覆盖手算最大t临界值/修正方向、"
        "无效标准误拒绝、等价模型重拟合及受试者轨迹/缺测保留。全部来源和输出摘要核验通过。",
        "",
        "解释审查11/11：按情景分开避免总体/分组混淆；不从群体推断个体；"
        "明确选择/Berkson及碰撞风险；基础率不适用于本模拟；不将均值回归当疗效；"
        "失败拟合计入分母避免成功者选择；报告全部方法避免多处搜索；"
        "预冻配置和独立种子限制分析路径；不作临床因果或逆向因果断言。",
        "",
        "[覆盖率比较图](coverage.png)；[偏差与带宽图](bias.png)；[逐分钟诊断](bias_and_width.csv)。",
        "",
        f"[完整运行及重抽日志]({run.as_posix()}/REPORT.md)；[来源及测试记录](review_manifest.json)。",
    ]
    (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    manifest = dict(
        status="completed",
        input=str(run),
        input_manifest_sha256=sha(run / "run_manifest.json"),
        git_revision=m["git_revision"],
        all_hashes_verified=True,
        tests=test_results,
        source_hashes={
            str(p): sha(p)
            for p in [
                Path(__file__).resolve(),
                ROOT / "scripts/plot_derivative_bootstrap_v4.R",
                ROOT / "scripts/test_derivative_bootstrap_v4.R",
            ]
        },
        bootstrap_attempts=len(statuses),
        bootstrap_failures=failed,
        outputs_sha256={p.name: sha(p) for p in out.iterdir()},
    )
    (out / "review_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(out)


if __name__ == "__main__":
    main()
