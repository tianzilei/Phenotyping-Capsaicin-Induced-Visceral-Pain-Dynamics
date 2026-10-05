"""Subject-refit calibration, immutable runs and gated independent validation."""

import argparse
import concurrent.futures
import csv
import hashlib
import json
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def wilson(k, n):
    z = 1.959963984540054
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / den
    return center - half, center + half


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["development", "validation"], required=True)
    parser.add_argument("--development-run", type=Path)
    args = parser.parse_args()
    cfgpath = ROOT / "config/derivative_calibration_v4.json"
    cfg = json.loads(cfgpath.read_text(encoding="utf-8"))
    sources = [cfgpath, Path(__file__).resolve()] + [
        ROOT / p
        for p in [
            "R/vas_models.R",
            "R/derivative_calibration.R",
            "R/derivative_candidate_v3.R",
            "R/derivative_bootstrap_v4.R",
            "scripts/run_derivative_bootstrap_v4.R",
            "scripts/derivative_v4_one_replicate.R",
            "config/derivative_v4_validation_execution.json",
        ]
    ]
    if args.phase == "validation":
        if not args.development_run:
            raise ValueError("Development run required")
        priorpath = args.development_run / "run_manifest.json"
        prior = json.loads(priorpath.read_text(encoding="utf-8"))
        if (
            prior["status"] != "completed"
            or prior["phase"] != "development"
            or not prior["gate_passed"]
        ):
            raise ValueError("Development gate did not pass")
        for p, h in prior["sources_sha256"].items():
            if sha(Path(p)) != h:
                raise ValueError(f"Development source changed: {p}")
        for p, h in prior["outputs_sha256"].items():
            if sha(args.development_run / p) != h:
                raise ValueError(f"Development output changed: {p}")
        sources.append(priorpath)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (
        ROOT
        / "02_quality_control"
        / f"derivative_v4_{args.phase}_{stamp}_{uuid.uuid4().hex[:8]}"
    )
    out.mkdir(parents=True, exist_ok=False)
    execution = json.loads(
        (ROOT / "config/derivative_v4_validation_execution.json").read_text(
            encoding="utf-8"
        )
    )
    state = dict(
        status="running",
        phase=args.phase,
        synthetic=True,
        created_utc=stamp,
        python=platform.python_version(),
        configuration=cfg,
        execution=execution,
        git_revision=subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip(),
        sources_sha256={str(p.resolve()): sha(p) for p in sources},
        commands=[],
    )

    def save():
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    save()
    print(json.dumps({"output": str(out), "phase": args.phase}), flush=True)
    jobs = []
    for i, (scenario, n) in enumerate(cfg["cells"]):
        cell = out / f"cell_{i + 1}_{scenario}_{n}"
        cell.mkdir()
        command = [
            "C:/Program Files/R/R-4.6.1/bin/Rscript.exe",
            str(ROOT / "scripts/run_derivative_bootstrap_v4.R"),
            str(ROOT),
            str(cell),
            scenario,
            str(n),
            str(cfg[args.phase + "_replicates"]),
            str(cfg["bootstrap_replicates"]),
            str(cfg[args.phase + "_seed"] + (i + 1) * 10000000),
            str(cfg["coefficient_draws"]),
        ]
        state["commands"].append(command)
        jobs.append((cell, command))
    save()
    cell_jobs = jobs
    jobs = []
    for replicate in range(1, cfg[args.phase + "_replicates"] + 1):
        for cell, command in cell_jobs:
            part = cell / f"replicate_{replicate:03d}"
            part.mkdir()
            cmd = command.copy()
            cmd[1] = str(ROOT / "scripts/derivative_v4_one_replicate.R")
            cmd[3] = str(part)
            cmd.append(str(replicate))
            jobs.append((part, cmd))
    state["commands"] = [cmd for _, cmd in jobs]
    save()

    def run(job):
        cell, command = job
        with (cell / "execution.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=cfg["timeout_per_cell_seconds"],
                check=False,
            )
        return cell, result.returncode

    try:
        codes = []
        completed_jobs = []
        futility = None
        next_job = iter(jobs)
        counts = {cell.name: dict(done=0, covered=0, valid=0) for cell, _ in cell_jobs}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=execution["workers"]
        ) as pool:
            pending = {}

            def submit_next():
                job = next(next_job, None)
                if job is not None:
                    pending[pool.submit(run, job)] = job

            for _ in range(execution["workers"]):
                submit_next()
            while pending:
                done, _ = concurrent.futures.wait(
                    pending, return_when=concurrent.futures.FIRST_COMPLETED
                )
                for future in done:
                    job = pending.pop(future)
                    cell, code = future.result()
                    codes.append(code)
                    completed_jobs.append(cell)
                    if code == 0:
                        with (cell / "replicates.csv").open(
                            encoding="utf-8", newline=""
                        ) as handle:
                            candidate = [
                                r
                                for r in csv.DictReader(handle)
                                if r["method"] == cfg["candidate"]
                            ]
                        if len(candidate) != 1:
                            raise ValueError("Invalid candidate row")
                        r = candidate[0]
                        c = counts[cell.parent.name]
                        c["done"] += 1
                        c["covered"] += r["simultaneous_coverage"] == "TRUE"
                        c["valid"] += r["success"] == "TRUE"
                        if (
                            args.phase == "validation"
                            and r["scenario"] != "informative_dropout"
                        ):
                            N = cfg["validation_replicates"]
                            remaining = N - c["done"]
                            best = c["covered"] + remaining
                            lo, _ = wilson(best, N)
                            impossible = (
                                best / N < 0.93
                                or lo < 0.90
                                or (c["valid"] + remaining) / N < 0.99
                            )
                            if impossible and futility is None:
                                futility = dict(
                                    cell=cell.parent.name,
                                    observed=dict(c),
                                    planned=N,
                                    optimistic_full_N_coverage=best / N,
                                    optimistic_Wilson_lower=lo,
                                    reason="Cannot pass even if every remaining planned sample is covered and valid",
                                )
                                print(json.dumps({"futility": futility}), flush=True)
                    print(
                        json.dumps(
                            {
                                "cell": cell.parent.name,
                                "replicate": cell.name,
                                "exit_code": code,
                            }
                        ),
                        flush=True,
                    )
                if futility is None and not any(codes):
                    while len(pending) < execution["workers"]:
                        before = len(pending)
                        submit_next()
                        if len(pending) == before:
                            break
        if any(codes):
            raise RuntimeError("Cell execution failed; logs retained")
        for cell, _ in cell_jobs:
            for filename in ("replicates.csv", "pointwise.csv", "bootstrap_status.csv"):
                merged = []
                for part in sorted(p for p in completed_jobs if p.parent == cell):
                    with (part / filename).open(encoding="utf-8", newline="") as handle:
                        merged.extend(csv.DictReader(handle))
                with (cell / filename).open(
                    "w", encoding="utf-8", newline=""
                ) as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(merged[0]))
                    writer.writeheader()
                    writer.writerows(merged)
        jobs = cell_jobs
        for p, h in state["sources_sha256"].items():
            if sha(Path(p)) != h:
                raise RuntimeError(f"Source mutated: {p}")
        rows = []
        summaries = []
        for cell, _ in jobs:
            with (cell / "replicates.csv").open(encoding="utf-8", newline="") as handle:
                current = list(csv.DictReader(handle))
            for method in cfg["methods"]:
                selected = [r for r in current if r["method"] == method]
                total = len(selected) if futility else cfg[args.phase + "_replicates"]
                if (
                    total == 0
                    or len(selected) != total
                    or len({r["replicate"] for r in selected}) != total
                ):
                    raise ValueError("Missing/duplicate replicates")
                covered = sum(r["simultaneous_coverage"] == "TRUE" for r in selected)
                valid = [r for r in selected if r["success"] == "TRUE"]
                lo, hi = wilson(covered, total)
                summaries.append(
                    dict(
                        scenario=selected[0]["scenario"],
                        n=int(selected[0]["n"]),
                        method=method,
                        replicates=total,
                        successes=len(valid),
                        coverage=covered / total,
                        wilson_lower=lo,
                        wilson_upper=hi,
                        boundary_coverage=sum(
                            r["boundary_coverage"] == "TRUE" for r in selected
                        )
                        / total,
                        interior_coverage=sum(
                            r["interior_coverage"] == "TRUE" for r in selected
                        )
                        / total,
                        mean_width=sum(float(r["mean_width"]) for r in valid)
                        / len(valid)
                        if valid
                        else None,
                        min_valid_bootstraps=min(
                            int(r["valid_bootstraps"]) for r in selected
                        ),
                    )
                )
            rows.extend(current)
        for name, data in [("replicates.csv", rows), ("summary.csv", summaries)]:
            with (out / name).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(data[0]))
                writer.writeheader()
                writer.writerows(data)
        candidate = [
            s
            for s in summaries
            if s["method"] == cfg["candidate"]
            and s["scenario"] != "informative_dropout"
        ]
        if len(candidate) != 5:
            raise ValueError("Missing calibration gate cells")
        if args.phase == "development":
            passed = all(
                s["coverage"] >= 0.90 and s["successes"] / s["replicates"] >= 0.98
                for s in candidate
            )
        else:
            passed = all(
                s["coverage"] >= 0.93
                and s["wilson_lower"] >= 0.90
                and s["successes"] / s["replicates"] >= 0.99
                for s in candidate
            )
        if futility:
            passed = False
        state.update(
            status="stopped_futility" if futility else "completed",
            summary=summaries,
            gate_passed=passed,
            futility=futility,
            completed_outer=len(completed_jobs),
            planned_outer=len(cfg["cells"]) * cfg[args.phase + "_replicates"],
        )
        lines = [
            "# 受试者重拟合与导数偏差修正",
            "",
            "## Material Passport",
            "",
            "- Origin Skill: academic-research-suite / experiment-agent",
            "- Origin Mode: run + validate",
            f"- Version: derivative_calibration_v4 / {args.phase}",
            "- Verification: SYNTHETIC；有限情景校准",
            "",
            f"预定候选门槛：{'通过' if passed else '未通过'}。失败拟合计作未覆盖。",
            "",
            (
                "按预先规定的“不可能达到门槛”规则提前停止；下表分母为实际完成数，不能称全部200次独立验证已完成。具体最乐观全样本上限见manifest。"
                if futility
                else "全部预定重复已完成。"
            ),
            "",
            "|情景|人数|方法|全网格覆盖|Wilson 95% 区间|边界覆盖|内部覆盖|平均带宽|成功数|最少成功重拟合|",
            "|---|---:|---|---:|---|---:|---:|---:|---:|---:|",
        ]
        for s in summaries:
            width = f"{s['mean_width']:.4f}" if s["mean_width"] is not None else "NA"
            lines.append(
                f"|{s['scenario']}|{s['n']}|{s['method']}|{s['coverage']:.1%}|"
                f"{s['wilson_lower']:.1%}–{s['wilson_upper']:.1%}|{s['boundary_coverage']:.1%}|"
                f"{s['interior_coverage']:.1%}|{width}|{s['successes']}/{s['replicates']}|{s['min_valid_bootstraps']}|"
            )
        lines += [
            "",
            "每个合成样本进行199次整人有放回重抽，重复抽中的人赋独立副本ID；"
            "缺测模式和实际时间原样保留，每次重新估计随机截距、CAR1及全部固定系数。"
            "基函数规格固定为无惩罚bs8，未重选节点或维数。要求至少196/199次有效，失败不补抽。",
            "",
            "原始bootstrap-t带以 (估计*−原估计)/SE* 的全网格最大绝对值校准；"
            "偏差修正中心为 2×原估计−bootstrap均值，临界值由 (估计*−bootstrap均值)/SE* 计算。"
            "这是待评估的单层偏差修正近似，并未为偏差估计额外构造二层不确定性校准。"
            "重抽不能保证识别或消除固定基函数逼近偏差；同时带仅针对1–20分钟网格。",
            "",
            "开发20次/格仅用于筛查，区间宽、不能证明标称覆盖。只有唯一预定候选在所有非信息性情景通过才进入200次/格独立验证；"
            "诊断方法不事后替代候选。独立验证未通过不得更新真实推断。",
            "",
            "信息性停止只作压力测试，生成总体导数不等于观察条件均值；不解决真实E/T停止选择。"
            "高斯模拟不截断，以保持解析真值；超量表数、全部重拟合错误和警告逐次记录。",
            "",
            "[汇总](summary.csv)；[逐重复](replicates.csv)；[配置、源码及所有子目录输出摘要](run_manifest.json)。",
        ]
        (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        state.update(status="failed", error=str(exc))
        raise
    finally:
        state["completed_utc"] = datetime.now(timezone.utc).isoformat()
        state["outputs_sha256"] = {
            str(p.relative_to(out)): sha(p)
            for p in out.rglob("*")
            if p.is_file() and p.name != "run_manifest.json"
        }
        save()
    print(json.dumps({"output": str(out), "gate_passed": passed}), flush=True)


if __name__ == "__main__":
    main()
