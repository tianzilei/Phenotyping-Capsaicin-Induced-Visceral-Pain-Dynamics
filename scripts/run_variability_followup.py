"""Frozen raw-variability follow-up; no derivative inference or imputation."""

import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.contracts import read_wide
from capsaicin.variability import window_metrics


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    with p.open(encoding="utf-8", newline="") as h:
        return list(csv.DictReader(h))


def write(p, rows):
    with p.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    cp = ROOT / "config/variability_followup_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    if (
        cfg["status"] != "frozen_provisional"
        or cfg["version"] != "variability_followup_v1"
    ):
        raise ValueError("Unfrozen config")
    prior = ROOT / cfg["input_run"]
    mp = prior / "run_manifest.json"
    m = json.loads(mp.read_text(encoding="utf-8"))
    if m["status"] != "completed_provisional":
        raise ValueError("Incomplete prior run")
    for name, h in m["outputs_sha256"].items():
        if sha(prior / name) != h:
            raise ValueError("Prior output changed")
    for name, h in m["input_sha256"].items():
        if sha(Path(name)) != h:
            raise ValueError("Prior input changed")
    data = next(
        Path(p) for p in m["input_sha256"] if p.endswith("BaselineData_E_coded.csv")
    )
    data_cfg = ROOT / "config/provisional_vas_v3.json"
    rows = read_wide(data, json.loads(data_cfg.read_text(encoding="utf-8")))
    previous = read(prior / "vas_long.csv")
    if len(rows) != len(previous):
        raise ValueError("Long input length mismatch")
    for a, b in zip(rows, previous):
        if any(
            str(a[k]) != b[k]
            for k in [
                "subject_id",
                "time_min",
                "status",
                "raw_token",
                "termination_code",
            ]
        ):
            raise ValueError("Long input differs")
        if a["vas"] != (float(b["vas"]) if b["vas"] else None):
            raise ValueError("Numeric data differs")
    sources = [
        cp,
        data,
        data_cfg,
        mp,
        prior / "vas_long.csv",
        Path(__file__).resolve(),
        ROOT / "src/capsaicin/variability.py",
        ROOT / "src/capsaicin/contracts.py",
        ROOT / "scripts/variability_followup.R",
        ROOT / "tests/test_variability.py",
    ]
    hashes = {str(p): sha(p) for p in sources}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "08_outputs" / f"variability_followup_{stamp}_{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "check-ignore",
            "--quiet",
            str(out.relative_to(ROOT) / "window_metrics_private.csv"),
        ],
        cwd=ROOT,
        check=True,
    )
    out.mkdir(parents=True, exist_ok=False)
    state = dict(
        status="running",
        started_utc=stamp,
        configuration=cfg,
        sources_sha256=hashes,
        python=platform.python_version(),
        git_revision=subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip(),
        prior_inputs_outputs_verified=True,
    )

    def save():
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    save()
    try:
        grouped = defaultdict(list)
        for r in rows:
            grouped[r["subject_id"]].append(r)
        metrics = []
        for sid, rs in grouped.items():
            markers = {
                r["termination_code"] for r in rs if r["termination_code"] in ("E", "T")
            }
            if len(markers) > 1:
                raise ValueError("Mixed stopping markers")
            marker = next(iter(markers), "none")
            for start, end in cfg["windows"]:
                z = window_metrics(rs, start, end)
                if z["mssd"] is not None and not math.isclose(
                    z["mssd"],
                    z["mean_adjacent_change"] ** 2 + z["centered_change_ms"],
                    abs_tol=1e-10,
                ):
                    raise ValueError("Decomposition failed")
                metrics.append(
                    dict(subject_id=sid, marker=marker, window=f"{start}_{end}", **z)
                )
        write(out / "window_metrics_private.csv", metrics)
        test_temp = out / "test_temp"
        test_temp.mkdir()
        env = dict(os.environ, TMP=str(test_temp), TEMP=str(test_temp))
        tests = subprocess.run(
            ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (out / "tests.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("Tests failed")
        cmd = [
            "C:/Program Files/R/R-4.6.1/bin/Rscript.exe",
            str(ROOT / "scripts/variability_followup.R"),
            str(out),
            str(cfg["bootstrap"]["replicates"]),
            str(cfg["bootstrap"]["seed"]),
        ]
        state["command"] = cmd
        with (out / "execution.log").open("w", encoding="utf-8") as log:
            p = subprocess.run(
                cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=600
            )
        if p.returncode:
            raise RuntimeError("R follow-up failed")
        summary = read(out / "window_summary.csv")
        counts = read(out / "eligibility_counts.csv")
        paired = read(out / "paired_early_late_summary.csv")
        report = [
            "# VAS原始波动与观察支持敏感性分析",
            "",
            "## Material Passport",
            "",
            "- Origin Skill: academic-research-suite / experiment-agent",
            "- Origin Mode: run + validate",
            "- Version: variability_followup_v1",
            "- Verification: PROVISIONAL；身份待核对，原始波动描述",
            "",
            f"本轮读取{len(grouped)}条候选受试者记录、{sum(r['status'] == 'observed' for r in rows)}个实测评分。"
            "与零值修复后的v3模型输入逐格一致。未修改E/T、零分、实际分钟或停止后缺测。",
            "",
            "MSSD为真实相邻分钟评分差的平方均值。它同时包含趋势和随机波动；"
            "本轮另给出平均相邻变化及中心化变化平方均值，满足MSSD=平均变化²+中心化变化平方均值，"
            "该代数分解仍不是去个体趋势后的不稳定性估计。RMSSD单位VAS，MSSD单位VAS²。",
            "",
            "|窗口（分钟）|至少3对人数|E/T/无标记|完整窗口人数|",
            "|---|---:|---|---:|",
        ]
        for start, end in cfg["windows"]:
            key = f"{start}_{end}"
            a = next(
                c
                for c in counts
                if c["window"] == key and c["policy"] == "at_least_3_pairs"
            )
            b = next(
                c
                for c in counts
                if c["window"] == key and c["policy"] == "complete_window"
            )
            report.append(
                f"|{start}–{end}|{a['n']}|{a['E']}/{a['T']}/{a['none']}|{b['n']}|"
            )
        report += [
            "",
            "|窗口|SD中位数|MSSD中位数|RMSSD中位数|平均相邻变化的中位数|",
            "|---|---:|---:|---:|---:|",
        ]
        for start, end in cfg["windows"]:
            z = {
                r["metric"]: r
                for r in summary
                if r["window"] == f"{start}_{end}" and r["policy"] == "at_least_3_pairs"
            }
            report.append(
                f"|{start}–{end}|"
                + "|".join(
                    f"{float(z[k]['median']):.4f}"
                    for k in ["sample_sd", "mssd", "rmssd", "mean_adjacent_change"]
                )
                + "|"
            )
        report += [
            "",
            "不同窗口的有效人群发生变化，不能将上表跨窗口差异直接解释为全体受试者的变化。"
            "按最终E/T分组仅用于描述入选构成，不作为基线暴露或因果分组。",
            "",
            "## 同一人早晚窗口对照",
            "",
            "只纳入1–5及16–20分钟均完整者，逐人计算晚期减早期，再对整人差值重抽2000次。"
            "该人群经过完整性选择，不能消除E/T退出带来的偏倚。",
            "",
            "|指标|配对人数|平均晚减早|探索性95%逐项bootstrap区间|",
            "|---|---:|---:|---|",
        ]
        for r in paired:
            report.append(
                f"|{r['metric']}|{r['n']}|{float(r['mean_late_minus_early']):.4f}|{float(r['bootstrap_lower']):.4f}–{float(r['bootstrap_upper']):.4f}|"
            )
        report += [
            "",
            "上述区间是逐项探索性百分位bootstrap区间，不是同时区间；不进行多个窗口/指标的显著性筛选或宣称确认性差异。"
            "窗口汇总同样采用整人等权重，不把相邻对当独立样本。",
            "",
            "## 关联与范围",
            "",
            "MSSD与平均VAS、有效相邻对数的Spearman关系按同窗口同入选人群分别输出，无p值；"
            "恒定变量的相关系数保持未定义。完整窗口对照与至少3对策略均保留，不按结果选择。",
            "",
            "离散评分会产生大量相同数值；有些中位数bootstrap区间上下限相同，这是本方法在当前样本下的输出，不能解释为总体指标没有不确定性。"
            "对小样本或离散中位数的标称覆盖未作独立校准，因此本轮区间只用于探索性描述。",
            "",
            "本轮完成M04原始波动描述和M08观察支持敏感性。个体去趋势、稀疏PACE、生理关联、Markov/耦合仍有方法或数据条件未满足；"
            "没有用占位统计量替代。导数区间校准失败限制继续有效。",
            "",
            "解释核查11/11：窗口人群分开避免总体/分组混淆；不从群体推断个体；"
            "E/T选择和碰撞风险保留；基础率不适用；不把均值回归解释为疗效；"
            "明确完整者选择；全部策略/指标报告；参数先冻结；不作因果或逆向因果判断。",
            "",
            "[窗口图](variability_windows.png)；[完整汇总与区间](window_summary.csv)；"
            "[相关描述](descriptive_correlations.csv)；[配对对照](paired_early_late_summary.csv)；"
            "[私有逐人指标](window_metrics_private.csv)；[来源、配置、测试及环境](run_manifest.json)。",
        ]
        (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        if any(sha(Path(p)) != h for p, h in hashes.items()):
            raise RuntimeError("Input/code mutated")
        state.update(
            status="completed_provisional",
            n_subject_rows=len(grouped),
            n_numeric=sum(r["status"] == "observed" for r in rows),
            tests_exit_code=tests.returncode,
        )
    except Exception as exc:
        state.update(status="failed", error=str(exc))
        raise
    finally:
        state["outputs_sha256"] = {
            str(p.relative_to(out)): sha(p)
            for p in out.rglob("*")
            if p.is_file() and p.name != "run_manifest.json"
        }
        save()
    print(out)


if __name__ == "__main__":
    main()
