"""Frozen, non-imputing missingness audit for the v3 VAS copy."""

import csv
import hashlib
import json
import math
import os
import statistics
import platform
import random
import subprocess
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.contracts import read_wide
from capsaicin.missingness import classify_all, adjacent_composition


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
    cp = ROOT / "config/missingness_audit_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    if (
        cfg["version"] != "missingness_audit_v1"
        or cfg["status"] != "frozen_provisional"
    ):
        raise ValueError("Unsupported configuration")
    prior = ROOT / cfg["input_run"]
    pm = prior / "run_manifest.json"
    m = json.loads(pm.read_text(encoding="utf-8"))
    if m["status"] != "completed_provisional":
        raise ValueError("Prior run incomplete")
    for n, h in m["outputs_sha256"].items():
        if sha(prior / n) != h:
            raise ValueError("Prior output changed")
    for n, h in m["input_sha256"].items():
        if sha(Path(n)) != h:
            raise ValueError("Prior input changed")
    data = next(
        Path(p) for p in m["input_sha256"] if p.endswith("BaselineData_E_coded.csv")
    )
    data_cfg = ROOT / "config/provisional_vas_v3.json"
    dc = json.loads(data_cfg.read_text(encoding="utf-8"))
    rows = read_wide(data, dc)
    prior_rows = read(prior / "vas_long.csv")
    if len(rows) != len(prior_rows):
        raise ValueError("Prior input length mismatch")
    for a, b in zip(rows, prior_rows):
        if any(
            str(a[k]) != b[k]
            for k in (
                "subject_id",
                "time_min",
                "status",
                "raw_token",
                "termination_code",
            )
        ):
            raise ValueError("Prior parse differs")
        if a["vas"] != (float(b["vas"]) if b["vas"] else None):
            raise ValueError("Prior value differs")
    sources = [
        cp,
        data,
        data_cfg,
        pm,
        prior / "vas_long.csv",
        Path(__file__).resolve(),
        ROOT / "src/capsaicin/missingness.py",
        ROOT / "src/capsaicin/contracts.py",
        ROOT / "tests/test_missingness.py",
        ROOT / "scripts/plot_missingness_audit.R",
    ]
    hashes = {str(p): sha(p) for p in sources}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "08_outputs" / f"missingness_audit_{stamp}_{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "check-ignore",
            "--quiet",
            str(out.relative_to(ROOT) / "subject_missingness_private.csv"),
        ],
        cwd=ROOT,
        check=True,
    )
    out.mkdir(parents=True, exist_ok=False)
    state = dict(
        status="running",
        configuration=cfg,
        created_utc=stamp,
        python=platform.python_version(),
        sources_sha256=hashes,
        git_revision=subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip(),
    )

    def save():
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    save()
    try:
        audit = classify_all(rows)
        write(out / "subject_missingness_private.csv", audit)
        decomposition = adjacent_composition(rows)
        for r in decomposition:
            if r["defined"] and not math.isclose(
                r["observed_mean_change"],
                r["paired_observed_change"] + r["composition_total"],
                abs_tol=1e-10,
            ):
                raise ValueError("Decomposition identity failed")
        write(out / "adjacent_mean_decomposition.csv", decomposition)
        minutes = range(1, 21)
        groups = defaultdict(list)
        for r in audit:
            groups[r["eventual_marker"]].append(r)
        counts = []
        for g, rs in [
            ("all", audit),
            ("E", groups["E"]),
            ("T", groups["T"]),
            ("none", groups["none"]),
        ]:
            for t in minutes:
                key = f"minute_{t}"
                c = defaultdict(int)
                for r in rs:
                    c[r[key]] += 1
                if sum(c.values()) != len(rs):
                    raise ValueError("Status count mismatch")
                counts.append(
                    dict(
                        group=g,
                        time_min=t,
                        n_subjects=len(rs),
                        observed=c["observed"],
                        termination_E=c["termination_E"],
                        termination_T=c["termination_T"],
                        pre_marker_missing=c["pre_marker_missing"],
                        post_termination_missing=c["post_termination_missing"],
                    )
                )
        write(out / "minute_missingness_counts.csv", counts)
        patterns = defaultdict(list)
        for r in audit:
            patterns[(r["eventual_marker"], r["pattern"])].append(r["subject_id"])
        pat = [
            dict(
                eventual_marker=k[0],
                pattern=k[1],
                n_subjects=len(v),
                subject_ids_private=";".join(v),
            )
            for k, v in sorted(patterns.items())
        ]
        write(out / "missingness_patterns_private.csv", pat)
        stats = []
        for g, rs in [
            ("all", audit),
            ("E", groups["E"]),
            ("T", groups["T"]),
            ("none", groups["none"]),
        ]:
            if not rs:
                continue
            for field in (
                "n_observed",
                "n_pre_marker_missing",
                "n_post_termination_missing",
                "longest_pre_marker_gap",
            ):
                vals = [r[field] for r in rs]
                stats.append(
                    dict(
                        group=g,
                        metric=field,
                        n=len(vals),
                        mean=sum(vals) / len(vals),
                        median=statistics.median(vals),
                        minimum=min(vals),
                        maximum=max(vals),
                    )
                )
        write(out / "subject_missingness_summary.csv", stats)
        # fixed subject bootstrap of proportions/count means, descriptive only
        randomizer = random.Random(cfg["bootstrap"]["seed"])
        boot = []
        for rep in range(cfg["bootstrap"]["replicates"]):
            sample = [audit[randomizer.randrange(len(audit))] for _ in audit]
            boot.append(
                dict(
                    rep=rep,
                    observed_fraction=sum(r["n_observed"] for r in sample)
                    / (len(sample) * 20),
                    pre_marker_fraction=sum(r["n_pre_marker_missing"] for r in sample)
                    / (len(sample) * 20),
                    post_term_fraction=sum(
                        r["n_post_termination_missing"] for r in sample
                    )
                    / (len(sample) * 20),
                )
            )
        write(out / "bootstrap_missingness_private.csv", boot)

        def q(vals, p):
            vals = sorted(vals)
            x = (len(vals) - 1) * p
            i = int(x)
            j = min(i + 1, len(vals) - 1)
            return vals[i] + (vals[j] - vals[i]) * (x - i)

        intervals = []
        for name, field in [
            ("observed_fraction", "n_observed"),
            ("pre_marker_fraction", "n_pre_marker_missing"),
            ("post_term_fraction", "n_post_termination_missing"),
        ]:
            intervals.append(
                dict(
                    metric=name,
                    estimate=sum(r[field] for r in audit) / (len(audit) * 20),
                    lower=q([b[name] for b in boot], 0.025),
                    upper=q([b[name] for b in boot], 0.975),
                    bootstrap_replicates=len(boot),
                )
            )
        write(out / "missingness_proportion_intervals.csv", intervals)
        temp = out / "test_temp"
        temp.mkdir()
        tests = subprocess.run(
            ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=ROOT,
            env=dict(os.environ, TMP=str(temp), TEMP=str(temp)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (out / "tests.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("Tests failed")
        # Plot counts and group composition
        plot = ROOT / "scripts/plot_missingness_audit.R"
        cmd = ["C:/Program Files/R/R-4.6.1/bin/Rscript.exe", str(plot), str(out)]
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

        def q(vals, p):
            vals = sorted(vals)
            x = (len(vals) - 1) * p
            i = int(x)
            j = min(i + 1, len(vals) - 1)
            return vals[i] + (vals[j] - vals[i]) * (x - i)

        report = [
            "# VAS缺失结构与E/T观察支持审计",
            "",
            "## Material Passport",
            "",
            "- Origin Skill: academic-research-suite / experiment-agent",
            "- Origin Mode: run + validate",
            "- Version: missingness_audit_v1",
            "- Verification: PROVISIONAL；描述性观察支持审计",
            "",
            f"本轮使用v3分析副本读取{len(audit)}行、{sum(r['n_observed'] for r in audit)}个实测评分；与既有模型逐格一致。E/T、零值、缺口和实际分钟未修改。",
            "",
            "分类规则：数字评分为observed；E/T为termination_E/termination_T；无既往标记的空缺为pre_marker_missing；已有标记后的空缺为post_termination_missing。无标记者的空缺也归入无既往标记空缺，不假定其未来是否终止或缺失原因。各比例的分母是组内人数×20个计划评分格，并非受试者比例。",
            "",
            "|组别|人数|数值评分比例|E编码比例|T编码比例|无既往标记空缺比例|标记后空缺比例|平均实测分钟数|",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for g, rs in [
            ("all", audit),
            ("E", groups["E"]),
            ("T", groups["T"]),
            ("none", groups["none"]),
        ]:
            if not rs:
                continue
            e_count = sum(
                r[f"minute_{t}"] == "termination_E" for r in rs for t in minutes
            )
            t_count = sum(
                r[f"minute_{t}"] == "termination_T" for r in rs for t in minutes
            )
            report.append(
                f"|{g}|{len(rs)}|{sum(r['n_observed'] for r in rs) / (len(rs) * 20):.3f}|{e_count / (len(rs) * 20):.3f}|{t_count / (len(rs) * 20):.3f}|{sum(r['n_pre_marker_missing'] for r in rs) / (len(rs) * 20):.3f}|{sum(r['n_post_termination_missing'] for r in rs) / (len(rs) * 20):.3f}|{sum(r['n_observed'] for r in rs) / len(rs):.2f}|"
            )
        report += [
            "",
            "E/T字母格与标记后的空白格必须合计才能描述全部停止相关非数值记录。“标记后空白为零”不意味着没有停止后未观测。重复字母格不是重复事件；E编码还包含此前16格由零转换的记录，原值仍在清单，不能把每个E格均认定为从未测量。",
            "",
            "E组与T组的分组只是最终标记的回顾性描述，不是基线暴露、随机分组或非信息性删失假设。首次标记列是编码位置，实际事件时间和逐例原因仍待核对。",
            "",
            "主要观察支持：每个受试者的20位状态字符串、每分钟计数、缺失模式和受试者汇总均已输出。2000次整人重抽仅描述数值评分格/无既往标记空缺格/标记后空缺格占全部计划评分格的比例波动；不是缺失机制校正，也不是反事实区间。全样本空白格为零时，经验bootstrap无法产生未见过的空白模式，零宽区间不证明总体缺失概率为零。",
            "",
            "不能把终止前缺口与终止后缺测合并后称为随机缺失；也不能把E后缺测填为零或T后填为高分。导数区间校准失败，不能从本表推导瞬时上升/下降时间。",
            "",
            "解释核查11/11：按组/总体分开；不作个体因果推断；选择与碰撞风险保留；不使用基础率或均值回归作结论；报告全部模式；参数预先冻结；不作因果或逆向因果判断。",
            "",
            "## 相邻分钟均值变化与观察人群构成",
            "",
            "逐分钟实测均值差 = 两分钟均有观测者的平均变化 + 起点构成项 + 终点构成项。构成项是描述性代数差，不是退出的因果效应；各分钟重叠人群不同，不能将各对的平均变化累加成同一固定队列轨迹。无重叠人群时保留未定义。",
            "",
            "|分钟对|两端人数|配对人数|均值变化|配对者变化|构成项合计|",
            "|---|---|---:|---:|---:|---:|",
        ]
        for r in decomposition:

            def fmt(v):
                return "未定义" if v is None else f"{v:.4f}"

            report.append(
                f"|{r['start_min']}–{r['end_min']}|{r['n_start']}/{r['n_end']}|{r['n_both']}|{fmt(r['observed_mean_change'])}|{fmt(r['paired_observed_change'])}|{fmt(r['composition_total'])}|"
            )
        report += [
            "",
            "[均值分解](adjacent_mean_decomposition.csv)；[比例及探索性区间](missingness_proportion_intervals.csv)；[分钟缺失计数](minute_missingness_counts.csv)；[缺失结构图](missingness_audit.png)；[受试者模式（私有）](subject_missingness_private.csv)；[模式汇总](missingness_patterns_private.csv)；[来源、配置与测试](run_manifest.json)。",
        ]
        (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        if any(sha(Path(p)) != h for p, h in hashes.items()):
            raise RuntimeError("Source mutated")
        state.update(
            status="completed_provisional",
            n_subjects=len(audit),
            n_numeric=sum(r["status"] == "observed" for r in rows),
            tests_exit_code=tests.returncode,
        )
    except Exception as e:
        state.update(status="failed", error=str(e))
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
