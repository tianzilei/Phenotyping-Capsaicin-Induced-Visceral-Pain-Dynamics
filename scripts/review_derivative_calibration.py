"""Summarize both completed development versions without modifying their outputs."""

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2", type=Path, required=True)
    parser.add_argument("--v3", type=Path, required=True)
    args = parser.parse_args()
    runs = []
    for path in (args.v2, args.v3):
        manifest = json.loads((path / "run_manifest.json").read_text(encoding="utf-8"))
        if manifest["status"] != "completed":
            raise ValueError("Refuse to summarize an incomplete run")
        expected = manifest["configuration"]["development_replicates"]
        if len(manifest["summary"]) != 24 or any(
            s["replicates"] != expected for s in manifest["summary"]
        ):
            raise ValueError("Incomplete scenario/method cells")
        for name, digest in manifest["outputs_sha256"].items():
            if sha(path / name) != digest:
                raise ValueError(f"Output digest mismatch: {path / name}")
        for name, digest in manifest["sources_sha256"].items():
            if sha(Path(name)) != digest:
                raise ValueError(f"Source changed: {name}")
        runs.append((path, manifest))
    out = (
        ROOT
        / "08_outputs"
        / (
            "derivative_calibration_review_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir(parents=True, exist_ok=False)
    checks = [["python", "-m", "unittest", "discover", "-s", "tests", "-v"]]
    for name in (
        "test_vas_models.R",
        "test_derivative_calibration.R",
        "test_derivative_candidate_v3.R",
    ):
        checks.append(
            ["C:/Program Files/R/R-4.6.1/bin/Rscript.exe", f"scripts/{name}", str(ROOT)]
        )
    statuses = []
    for i, command in enumerate(checks):
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (out / f"tests_{i}.log").write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
        statuses.append(dict(command=command, exit_code=result.returncode))
        if result.returncode:
            raise RuntimeError("Verification failed")
    if any(m["candidate_gate_passed"] for _, m in runs):
        raise ValueError(
            "Review narrative expects failed development gates; inspect before reporting"
        )
    lines = [
        "# 导数置信带校准复核",
        "",
        "## Material Passport",
        "",
        "- Origin Skill: academic-research-suite / experiment-agent",
        "- Origin Mode: run + validate",
        "- Verification Status: ANALYZED；工程测试通过，统计校准未通过",
        "- Version Label: derivative_calibration_v2 + v3",
        "",
        "**本轮已完成两版方法开发与合成校准。两版预定候选均未通过开发门槛，未启动独立验证，也未替换真实数据 v3 模型。**",
        "",
        "原自然三次样条的边界约束是已确认的偏差来源：在无噪声二次曲线中，"
        "即使不施加平滑惩罚，k=6 的端点导数偏差仍约为 ±0.04716 VAS/分钟，"
        "k=10 约为 ±0.02379；无自然边界约束的固定 B 样条可重现该二次曲线。"
        "但修正这个问题不自动保证其他曲线和缺测条件下的区间覆盖。",
        "",
        "|版本|情景|人数|方法|全网格覆盖|Wilson 95% 区间|端点覆盖|内部覆盖|平均带宽|成功拟合|",
        "|---|---|---:|---|---:|---|---:|---:|---:|---:|",
    ]
    for path, m in runs:
        version = m["configuration"]["version"]
        for s in m["summary"]:
            lines.append(
                f"|{version}|{s['scenario']}|{s['n']}|{s['method']}|{s['coverage']:.1%}|"
                f"{s['wilson_lower']:.1%}–{s['wilson_upper']:.1%}|{s['boundary_coverage']:.1%}|"
                f"{s['interior_coverage']:.1%}|{s['mean_width']:.4f}|{s['successes']}/{s['replicates']}|"
            )
    lines += [
        "",
        "所有覆盖率以全部预定重复为分母，失败拟合计为未覆盖。区间针对固定的 20 个分钟网格；"
        "不声称覆盖连续时间的所有点。Wilson 区间表示各情景覆盖率估计的 Monte Carlo 不确定性，"
        "不作跨情景联合置信声明。平均带宽单位为 VAS/分钟。",
        "",
        "## 方法结论",
        "",
        "第一版预定候选为固定 6 系数 B 样条加 CR1/t 带：它能缓解二次曲线的边界偏差，"
        "但在波形情景中基函数表达不足。看到该开发失败后，第二版增加到 8 系数并加入 CR2 杠杆修正，"
        "另保留 10 系数作为诊断；第二版唯一预定候选也未通过。没有把诊断候选事后改成“获胜方法”。",
        "",
        "信息性退出场景单独作为压力测试，真值为生成总体均值的导数。"
        "它与仍有观测者条件均值不同，不能据此认为已经识别真实 E/T 停止后的完整随访轨迹。"
        "合成数据采用未截断高斯误差以保留解析真值，超量表观测数逐重复记录；"
        "本轮也没有覆盖所有真实量表边界、强相关和异方差情景。",
        "",
        "## 对当前分析的影响",
        "",
        "保留已修复编码的真实数据及原 GAMM/FPCA 结果用于暂定描述。"
        "原导数带不能用于发布“显著上升/下降的时间段”；原文件中的 increasing/decreasing 标签仅是旧模型计算输出，"
        "不提升为经校准的证据。本轮不从这些标签提取最终结论。",
        "",
        "后续方法工作需要另冻方案：可评估受试者层面重拟合的同时带、平滑偏差修正，"
        "或经科学确认改用固定时间间隔的平均变化率。后者会改变估计对象，不能悄悄替代瞬时导数。"
        "身份与真实停止时间核对仍可继续；不需要为未通过校准的模型反复重跑临床数据。",
        "",
        "## 验证与文件",
        "",
        "64 项 Python 合成测试及三组 R 检查通过，包含端点多项式重现、GLS 协方差独立计算、"
        "受试者顺序不变性和 CR2 在已知工作协方差下的期望恒等式。输入、配置、脚本和结果 SHA256 均核验。"
        "R 启动有系统 locale 警告；逐次拟合的收敛警告和错误另存，不把拟合失败隐藏。",
        "",
        "解释审查 11/11 已覆盖：分层与总体混淆、生态推断、选择/Berkson、碰撞偏倚、基础率、均值回归、"
        "幸存者偏倚、多重搜索、分析路径自由度、相关因果混淆和逆向因果；"
        "不适用项注明于[方法说明](../../docs/derivative_calibration.md)。这不意味着所有偏倚已消除。",
        "",
    ]
    for p, m in runs:
        lines.append(
            f"- [{m['configuration']['version']} 完整报告]({p.resolve().as_posix()}/REPORT.md)"
        )
    lines += [
        "- [无噪声端点诊断](../../02_quality_control/derivative_basis_check_20260916_v1/noiseless_basis_bias.csv)",
        "- [来源、环境与测试日志索引](review_manifest.json)",
    ]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    state = dict(
        status="completed_calibration_not_passed",
        python=platform.python_version(),
        git_revision=runs[0][1]["git_revision"],
        inputs_sha256={
            str((p / "run_manifest.json").resolve()): sha(p / "run_manifest.json")
            for p, _ in runs
        },
        sources_sha256={
            str(p.resolve()): sha(p)
            for p in [
                Path(__file__),
                ROOT / "scripts/test_vas_models.R",
                ROOT / "scripts/test_derivative_calibration.R",
                ROOT / "scripts/test_derivative_candidate_v3.R",
            ]
        },
        tests=statuses,
        real_model_unchanged=True,
        independent_validation_executed=False,
        outputs_sha256={p.name: sha(p) for p in out.iterdir()},
    )
    (out / "review_manifest.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )
    print(out)


if __name__ == "__main__":
    main()
