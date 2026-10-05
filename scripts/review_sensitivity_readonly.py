"""Verify historical sensitivity tables without modifying any source run."""

import collections
import csv
import json
import os
import platform
import statistics
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from audit_signal_readiness import ROOT, sha
from run_signal_spectra import write_rows
from path_resolver import resolve_input
from capsaicin.hash_baseline import check_reference


def read(path):
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def close(actual, expected):
    if actual in ("", None):
        if expected is not None:
            raise AssertionError("Missing defined value")
    elif expected is None or abs(float(actual) - expected) > 1e-12:
        raise AssertionError("Numeric mismatch")


def verify_tables(raw, syn, summ, baseline, synthetic_summary):
    groups = collections.defaultdict(dict)
    for r in raw:
        key = (r["path"], r["channel"], r["window_index"])
        a = int(r["amplitude_multiplier"])
        e = int(r["energy_multiplier"])
        if a != e or a in groups[key] or a not in (2, 3, 4, 5):
            raise AssertionError("Duplicate/invalid scenario key")
        groups[key][a] = r
        aa = int(r["amplitude_candidates"])
        ee = int(r["energy_candidates"])
        mm = int(r["matched"])
        if not 0 <= mm <= min(aa, ee):
            raise AssertionError("Invalid matched count")
        close(r["agreement"], 2 * mm / (aa + ee) if aa + ee else None)
    if any(set(g) != {2, 3, 4, 5} for g in groups.values()):
        raise AssertionError("Missing scenario")
    base = {(r["path"], r["channel"], r["window_index"]): r for r in baseline}
    if len(base) != len(baseline) or set(base) != set(groups):
        raise AssertionError("Baseline support differs")
    for key, b in base.items():
        r = groups[key][3]
        for s, t in [
            ("amplitude_candidates", "amplitude_candidate_count"),
            ("energy_candidates", "energy_candidate_count"),
            ("matched", "matched"),
        ]:
            if int(r[s]) != int(b[t]):
                raise AssertionError("Baseline count mismatch")
        close(r["agreement"], float(b["agreement"]) if b["agreement"] else None)
    if len(summ) != 4 or {int(r["amplitude_multiplier"]) for r in summ} != {2, 3, 4, 5}:
        raise AssertionError("Summary scenarios differ")
    for s in summ:
        a = int(s["amplitude_multiplier"])
        g = [v[a] for v in groups.values()]
        if int(s["energy_multiplier"]) != a or int(s["channel_windows"]) != len(g):
            raise AssertionError("Summary support differs")
        for col in ("amplitude_candidates", "energy_candidates"):
            if int(s[col]) != sum(int(r[col]) for r in g):
                raise AssertionError("Summary total mismatch")
        values = [float(r["agreement"]) for r in g if r["agreement"] != ""]
        close(s["median_agreement"], statistics.median(values) if values else None)
        close(
            s["low_agreement_fraction"],
            sum(v < 0.5 for v in values) / len(values) if values else None,
        )
    keys = set()
    sg = collections.defaultdict(list)
    for r in syn:
        key = (
            r["case"],
            r["replicate"],
            r["amplitude_multiplier"],
            r["energy_multiplier"],
            r["method"],
        )
        if key in keys:
            raise AssertionError("Duplicate synthetic key")
        keys.add(key)
        n = int(r["candidate_count"])
        truth = int(r["truth_count"])
        matched = int(r["matched"])
        if (
            not 0 <= matched <= min(n, truth)
            or int(r["false_candidates"]) != n - matched
        ):
            raise AssertionError("Invalid synthetic counts")
        close(r["precision"], matched / n if n else None)
        close(r["recall"], matched / truth if truth else None)
        sg[(r["case"], r["amplitude_multiplier"], r["energy_multiplier"])].append(r)
    if len(synthetic_summary) != len(sg):
        raise AssertionError("Synthetic summary support differs")
    for s in synthetic_summary:
        g = sg[(s["case"], s["amplitude_multiplier"], s["energy_multiplier"])]
        for method in ("amplitude", "energy"):
            selected = [r for r in g if r["method"] == method]
            for field, source in [
                (method + "_candidates", "candidate_count"),
                ("false_" + method, "false_candidates"),
            ]:
                if int(s[field]) != sum(int(r[source]) for r in selected):
                    raise AssertionError("Synthetic summary mismatch")
    increases = []
    for key, g in groups.items():
        for a in (2, 3, 4):
            for method in ("amplitude", "energy"):
                delta = int(g[a + 1][method + "_candidates"]) - int(
                    g[a][method + "_candidates"]
                )
                if delta > 0:
                    increases.append(
                        dict(
                            path=key[0],
                            channel=key[1],
                            window_index=key[2],
                            method=method,
                            from_multiplier=a,
                            count_increase=delta,
                        )
                    )
    return dict(
        channel_windows=len(groups),
        raw_rows=len(raw),
        synthetic_rows=len(syn),
        baseline_window_matches=len(base),
        observed_count_increases=len(increases),
    ), increases


def main():
    run = ROOT / sys.argv[1]
    mp = run / "run_manifest.json"
    m = json.loads(mp.read_text(encoding="utf-8"))
    if m["status"] != "completed_sensitivity_descriptions":
        raise ValueError("Incomplete source")
    out = (
        ROOT
        / "08_outputs"
        / (
            "ecg_sensitivity_review_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    subprocess.run(
        git + ["check-ignore", "--quiet", str(out / "code_drift_private.csv")],
        cwd=ROOT,
        check=True,
    )
    before = {str(p): sha(p) for p in run.rglob("*") if p.is_file()}
    verified = 0
    drift = []
    for field in ("inputs_sha256", "signals_sha256", "outputs_sha256"):
        for name, digest in m[field].items():
            p = run / name if field == "outputs_sha256" else resolve_input(name)
            actual = sha(p)
            if actual != digest:
                status = check_reference(mp, field, name, digest, p)
                drift.append(
                    dict(
                        path=str(p),
                        historical_sha256=digest,
                        current_sha256=actual,
                        status=status,
                    )
                )
            else:
                verified += 1
    cp = ROOT / "config/analysis_closeout_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    base = ROOT / cfg["baseline_candidate_run"]
    bp = base / "windows_private.csv"
    bm = json.loads((base / "run_manifest.json").read_text(encoding="utf-8"))
    if sha(bp) != bm["outputs_sha256"]["windows_private.csv"]:
        raise AssertionError("Baseline changed")
    result, increases = verify_tables(
        read(run / "raw_sensitivity_private.csv"),
        read(run / "synthetic_sensitivity.csv"),
        read(run / "raw_sensitivity_summary.csv"),
        read(bp),
        read(run / "synthetic_sensitivity_summary.csv"),
    )
    assert result["raw_rows"] == 9216 and result["synthetic_rows"] == 560
    result.update(
        status="verified_existing_tables",
        verified_hashes=verified,
        code_drift_files=len(drift),
        clinical_qc_passed=False,
    )
    write_rows(out / "code_drift_private.csv", drift)
    write_rows(out / "count_increases_private.csv", increases)
    tmp = out / "test_temp"
    tmp.mkdir()
    with (out / "tests.log").open("w", encoding="utf-8") as f:
        subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=ROOT,
            stdout=f,
            stderr=subprocess.STDOUT,
            env=dict(os.environ, TMP=str(tmp), TEMP=str(tmp)),
            check=True,
        )
    report = [
        "# 心电阈值敏感性只读复核与更正",
        "",
        "## Material Passport",
        "",
        "- Origin Skill: academic-research-suite / experiment-agent",
        "- Origin Mode: validate",
        "- Verification: 既有表格与基准逐窗一致；未声称全部情景重新提取",
        "",
        "全部9216个实测情景行、560个合成行重新核对；2304个乘数3窗口的候选数、匹配数和一致度与D46精确相同。合成精确率、召回率及汇总计数重算通过。",
        "",
        "本数据逐窗计数在2→3、3→4、4→5均未增加；这只是观察性质。不应期按分数贪心保留可在候选集合缩小时释放邻峰，不能把单调性当通用保证。",
        "",
        "D47仅保存各情景计数，没有保存乘数2/4/5的逐候选时间。D46时间向量仅对应乘数3，不可沿用为其他情景。原报告这一表述在此更正，旧文件保留。原<0.5比例未在配置中预先定义，本次只核对历史计算，不作为QC标准。",
        "",
        f"核验{verified}项哈希；另有{len(drift)}份现行代码相对历史摘要变化，逐项列出，未替换历史摘要或当作原始数据变动。D47第一次运行因读取不存在的label列失败，仅留下测试目录；随后修正另建成功运行，本轮不回填旧清单。",
        "",
        "MAD乘数2/3/4/5的两法一致度中位为0.717/0.772/0.912/0.994。候选总数同时减少，但不能由共变推出一致性提升的原因或真实准确率；纯噪声在乘数5仍有每100秒159.4/46.5个假候选。没有选择最佳阈值、发布HRV。",
        "",
        "11项解释检查覆盖：分组反转、生态推断、选择与碰撞偏倚、基率、均值回归、完整者偏倚、多重比较、分析分支、因果与反向因果。本轮无推断检验；窗口不是独立受试者，情景不等于临床验收。",
        "",
        f"[源汇总](../{run.name}/raw_sensitivity_summary.csv) · [核验](verification.json)",
    ]
    (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    if before != {str(p): sha(p) for p in run.rglob("*") if p.is_file()}:
        raise AssertionError("Source modified")
    result["source_run_unchanged"] = True
    (out / "verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    sources = [
        mp,
        cp,
        bp,
        base / "run_manifest.json",
        Path(__file__).resolve(),
        ROOT / "scripts/audit_signal_readiness.py",
        ROOT / "scripts/run_signal_spectra.py",
        ROOT / "tests/test_ecg_candidate_sensitivity.py",
        ROOT / "tests/test_sensitivity_review.py",
    ]
    state = dict(
        status="completed_read_only_review",
        created_utc=datetime.now(timezone.utc).isoformat(),
        python=platform.python_version(),
        git_revision=subprocess.check_output(
            git + ["rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        inputs_sha256={str(p): sha(p) for p in sources},
        outputs_sha256={
            str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()
        },
    )
    (out / "run_manifest.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )
    print(out)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
