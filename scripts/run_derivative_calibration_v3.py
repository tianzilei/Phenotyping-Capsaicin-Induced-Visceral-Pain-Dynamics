"""Frozen synthetic comparison with hashes, independent seeds and explicit gates."""

import argparse
import csv
import hashlib
import json
import math
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wilson(k, n):
    p = k / n
    z = 1.959963984540054
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return center - half, center + half


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["development", "validation"], required=True)
    parser.add_argument("--development-run", type=Path)
    parser.add_argument(
        "--rscript", default="C:/Program Files/R/R-4.6.1/bin/Rscript.exe"
    )
    args = parser.parse_args()
    cfg_path = ROOT / "config/derivative_calibration_v3.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    sources = [
        cfg_path,
        ROOT / "R/vas_models.R",
        ROOT / "R/derivative_calibration.R",
        ROOT / "R/derivative_candidate_v3.R",
        ROOT / "scripts/run_derivative_calibration_v3.R",
        Path(__file__).resolve(),
    ]
    if args.phase == "validation":
        if not args.development_run:
            raise ValueError(
                "Independent validation requires a completed development run"
            )
        manifest = args.development_run / "run_manifest.json"
        prior = json.loads(manifest.read_text(encoding="utf-8"))
        if prior["status"] != "completed" or not prior["candidate_gate_passed"]:
            raise ValueError("Development gate did not pass")
        for path, digest in prior["sources_sha256"].items():
            if sha(Path(path)) != digest:
                raise ValueError(
                    f"Code/configuration changed since development: {path}"
                )
        sources.append(manifest)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (
        ROOT
        / "02_quality_control"
        / f"derivative_v3_{args.phase}_{stamp}_{uuid.uuid4().hex[:8]}"
    )
    out.mkdir(parents=True, exist_ok=False)
    hashes = {str(p): sha(p) for p in sources}
    revision = subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    state = dict(
        status="running",
        phase=args.phase,
        created_utc=stamp,
        synthetic=True,
        python=platform.python_version(),
        git_revision=revision,
        sources_sha256=hashes,
        configuration=cfg,
        output=str(out),
    )

    def save():
        (out / "run_manifest.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )

    save()
    command = [
        args.rscript,
        str(ROOT / "scripts/run_derivative_calibration_v3.R"),
        str(ROOT),
        str(out),
        str(cfg[args.phase + "_replicates"]),
        str(cfg[args.phase + "_seed"]),
        str(cfg["coefficient_draws"]),
        args.phase,
    ]
    state["command"] = command
    print(json.dumps({"output": str(out), "phase": args.phase}), flush=True)
    try:
        with (out / "execution.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=3600,
                check=False,
            )
        state["exit_code"] = completed.returncode
        if completed.returncode:
            raise RuntimeError(f"R failed: see {out}/execution.log")
        if any(sha(Path(p)) != h for p, h in hashes.items()):
            raise RuntimeError("Source/configuration mutated during run")
        with (out / "replicates.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        summaries = []
        for key in sorted({(r["scenario"], int(r["n"]), r["method"]) for r in rows}):
            selected = [
                r for r in rows if (r["scenario"], int(r["n"]), r["method"]) == key
            ]
            total = len(selected)
            success = sum(r["success"] == "TRUE" for r in selected)
            covered = sum(r["simultaneous_coverage"] == "TRUE" for r in selected)
            lo, hi = wilson(covered, total)
            good = [r for r in selected if r["success"] == "TRUE"]
            summaries.append(
                dict(
                    scenario=key[0],
                    n=key[1],
                    method=key[2],
                    replicates=total,
                    successes=success,
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
                    mean_width=sum(float(r["mean_width"]) for r in good) / len(good)
                    if good
                    else None,
                )
            )
        with (out / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
            writer.writeheader()
            writer.writerows(summaries)
        candidates = [
            s
            for s in summaries
            if s["method"] == "bs8_cr2_t" and s["scenario"] != "informative_dropout"
        ]
        if args.phase == "development":
            passed = all(
                s["coverage"] >= 0.90 and s["successes"] / s["replicates"] >= 0.98
                for s in candidates
            )
        else:
            passed = all(
                s["coverage"] >= 0.93
                and s["wilson_lower"] >= 0.90
                and s["successes"] / s["replicates"] >= 0.99
                for s in candidates
            )
        state.update(
            status="completed",
            candidate_gate_passed=passed,
            summary=summaries,
            failure_policy="failed fits count as noncoverage",
            inference_scope="limited synthetic scenarios; no resolution of informative clinical dropout",
        )
        lines = [
            "# 导数区间合成校准",
            "",
            "Material Passport: academic-research-suite / experiment-agent; "
            f"{args.phase}; derivative_calibration_v3; SYNTHETIC",
            "",
            f"预设候选方法门槛：{'通过' if passed else '未通过'}。拟合失败计入覆盖率分母。",
            "",
            "|场景|人数|方法|覆盖率|Wilson 95% 区间|边界覆盖|内部覆盖|成功数|",
            "|---|---:|---|---:|---|---:|---:|---:|",
        ]
        for s in summaries:
            lines.append(
                f"|{s['scenario']}|{s['n']}|{s['method']}|{s['coverage']:.1%}|"
                f"{s['wilson_lower']:.1%}–{s['wilson_upper']:.1%}|{s['boundary_coverage']:.1%}|"
                f"{s['interior_coverage']:.1%}|{s['successes']}/{s['replicates']}|"
            )
        lines += [
            "",
            "固定每分钟网格的解析总体均值导数；边界为 1/20 分钟，内部为 2–19 分钟。"
            "cr 方法为原自然三次样条条件系数带；bs8/bs10 为固定节点、无惩罚三次 B 样条混合模型，"
            "cr1_t 使用受试者 GLS 得分夹心协方差；cr2_t 另作受试者杠杆修正，均使用共同 t 尺度抽样。",
            "",
            "该比较尚不证明在任意曲线下具有标称覆盖。高斯模拟值不截断为 0–10，以免改变解析真值；"
            "超界值数量逐重复记录。信息性退出场景仅作压力测试，其真值为生成总体均值，"
            "不等于仍有观测者的条件均值；不以其表现宣称已解决真实 E/T 停止选择。",
            "",
            "开发与验证使用不同数据种子；不得按验证结果继续调参后沿用本次验证通过的说法。",
            "",
            "[逐分钟偏差图](coverage_diagnostics.png)；[汇总](summary.csv)；[逐重复](replicates.csv)；"
            "[逐分钟估计](pointwise.csv)；[来源与环境](run_manifest.json)。",
        ]
        (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        state.update(status="failed", error=str(exc))
        raise
    finally:
        state["outputs_sha256"] = {
            p.name: sha(p) for p in out.iterdir() if p.name != "run_manifest.json"
        }
        save()
    print(json.dumps({"output": str(out), "gate_passed": passed}), flush=True)


if __name__ == "__main__":
    main()
