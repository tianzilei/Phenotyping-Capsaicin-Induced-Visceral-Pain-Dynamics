"""Verify and summarize the narrowly authorized E recoding and completed refits."""

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.cli import digest, write_json, write_csv
from capsaicin.analysis import csv_rows


def verify(folder, name="run_manifest.json"):
    manifest = json.loads((folder / name).read_text(encoding="utf-8"))
    if not manifest["status"].startswith("completed"):
        raise RuntimeError("Incomplete run")
    assert all(digest(folder / p) == h for p, h in manifest["outputs_sha256"].items())
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.add_argument("--followup", required=True)
    p.add_argument("--prepared", required=True)
    args = p.parse_args()
    old, new, follow, prepared = [
        Path(x).resolve() for x in (args.old, args.new, args.followup, args.prepared)
    ]
    oldm = verify(old)
    newm = verify(new)
    fm = verify(follow)
    pm = verify(prepared, "preparation_manifest.json")
    for m in (newm, fm, pm):
        assert all(digest(Path(path)) == h for path, h in m["input_sha256"].items())
    oldrows = csv_rows(old / "vas_long.csv")
    newrows = csv_rows(new / "vas_long.csv")
    changes = csv_rows(prepared / "cell_changes_private.csv")
    connected = pm["rule_version"] == "e_zero_recode_v2"
    authorized = {(r["subject_id"], int(r["time_min"])) for r in changes}
    assert len(authorized) == 8
    assert len(oldrows) == len(newrows)
    changed_raw = []
    for a, b in zip(oldrows, newrows):
        assert (a["subject_id"], a["time_min"]) == (b["subject_id"], b["time_min"])
        key = (a["subject_id"], int(a["time_min"]))
        if a["raw_token"] != b["raw_token"]:
            changed_raw.append(key)
            assert (
                key in authorized
                and float(a["vas"]) == 0
                and b["raw_token"] == "E"
                and b["vas"] == ""
            )
        else:
            assert a == b
    assert set(changed_raw) == authorized

    def compare_csv(filename, key, fields):
        a = {tuple(r[k] for k in key): r for r in csv_rows(old / filename)}
        b = {tuple(r[k] for k in key): r for r in csv_rows(new / filename)}
        result = []
        for k in a.keys() & b.keys():
            for field in fields:
                result.append(
                    dict(
                        table=filename,
                        row_key="|".join(k),
                        metric=field,
                        old=float(a[k][field]),
                        new=float(b[k][field]),
                        difference=float(b[k][field]) - float(a[k][field]),
                    )
                )
        return result

    comparison = []
    for filename, key, fields in [
        ("gamm_curve.csv", ["time_min"], ["estimate"]),
        ("gamm_derivatives.csv", ["time_min"], ["estimate"]),
        (
            "fpca_complete_1_20_eigenvalues.csv",
            ["component"],
            ["FVE", "cumulative_FVE"],
        ),
        (
            "fpca_complete_1_10_eigenvalues.csv",
            ["component"],
            ["FVE", "cumulative_FVE"],
        ),
    ]:
        comparison.extend(compare_csv(filename, key, fields))
    out = (
        ROOT
        / "08_outputs"
        / (
            "e_coding_review_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    write_csv(out / "aggregate_comparison.csv", comparison)
    oldoverview = json.loads((old / "data_overview.json").read_text())
    newoverview = json.loads((new / "data_overview.json").read_text())
    summary = json.loads((follow / "summary.json").read_text())
    curve_change = max(
        abs(r["difference"]) for r in comparison if r["table"] == "gamm_curve.csv"
    )
    derivative_change = max(
        abs(r["difference"]) for r in comparison if r["table"] == "gamm_derivatives.csv"
    )
    status = csv_rows(new / "gamm_bootstrap_status.csv")
    tests = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    (out / "tests.log").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    lines = [
        "# E 编码修正与分析重跑",
        "",
        "## Material Passport",
        "",
        "- Origin Skill: academic-research-suite / experiment-agent",
        "- Origin Mode: run + validate",
        "- Verification Status: PROVISIONAL；授权编码修正已核验，统计校准限制保留",
        f"- Version Label: {newm['config_version']} / {fm['configuration_version']}",
        "",
        "**用户确认已有 E 是处理后的编码。因此撤回旧报告中“146 行 E 前非双零需要核对”的解释。**",
        (
            "本轮将已有 E 前的剩余连续零段完整编码为 E，4 行长度为 3/1/2/2，共再改 8 格；加上第一轮累计 16 格。29 个不与 E 相连的零值保留。规则再次应用不产生修改。"
            if connected
            else "本次仅将先前识别的 4 行中、紧邻原首次 E 前的两格零改为 E，共 8 格。"
        )
        + "其他单元格及所有 T 保持不变；原 CSV 未改动，新副本及逐格旧值/新值清单单独保存。",
        "首次编码 E 前移不等于实际停止时刻前移；上一版本首次 E 位置保存在清单。没有补写基线、停止后评分或改写不相连的零值。",
        "",
        "|检查项|结果|",
        "|---|---|",
        f"|候选行数|{newoverview['candidate_rows']}，不变|",
        f"|有效数值评分|{oldoverview['observed_values']} → {newoverview['observed_values']}|",
        f"|完整 1–20 分钟行数|{newoverview['complete_1_20']}|",
        f"|GAMM 整人 bootstrap|{sum(r['success'] == 'TRUE' for r in status)}/{len(status)} 成功|",
        f"|群体曲线相对旧运行的最大绝对变化|{curve_change:.6f} VAS|",
        f"|导数相对旧运行的最大绝对变化|{derivative_change:.6f} VAS/分钟|",
        f"|E 编码复核|{summary['E_recorded_support']}|",
        f"|实测均值整人 bootstrap|{summary['bootstrap_replicates']} 次；每分钟至少 {summary['minimum_bootstrap_valid']} 次有效|",
        "",
        "GAMM/导数、200 次模型重采样、有限敏感性和两个区间完整者 FPCA 均重跑；E/T 分布、实测均值区间和量表数学范围以新副本重算。原配置和旧结果保持，不能混用旧模型与新编码后的事件表。",
        "此前导数 95% 同时带在弯曲退出合成情景的经验覆盖不足仍未解决，本次编码修正不代表统计校准完成。身份、访视及实际停止时间待核实；生理、Markov、稀疏 PACE 等未就绪模块未被伪装为已运行。",
        "",
        "## 文件入口",
        "",
        f"- [修正后的分析数据]({(prepared / 'BaselineData_E_coded.csv').as_posix()})",
        f"- [8 格修改清单（私有）]({(prepared / 'cell_changes_private.csv').as_posix()})",
        f"- [重跑模型报告]({(new / 'REPORT.md').as_posix()})",
        f"- [重算 E/T 补充报告]({(follow / 'REPORT.md').as_posix()})",
        "- [新旧汇总结果比较](aggregate_comparison.csv)",
        "- [输入、结果与测试核验](review_manifest.json)",
    ]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(
        out / "review_manifest.json",
        dict(
            created_utc=datetime.now(timezone.utc).isoformat(),
            status="completed" if tests.returncode == 0 else "failed_tests",
            git_commit=newm["git_commit"],
            python=sys.version,
            sources={
                str(folder / name): digest(folder / name)
                for folder, name in [
                    (old, "run_manifest.json"),
                    (new, "run_manifest.json"),
                    (follow, "run_manifest.json"),
                    (prepared, "preparation_manifest.json"),
                ]
            },
            exact_eight_authorized_cells_verified=True,
            all_source_and_output_hashes_verified=True,
            tests_exit_code=tests.returncode,
            script_sha256=digest(Path(__file__)),
            outputs_sha256={p.name: digest(p) for p in out.iterdir() if p.is_file()},
        ),
    )
    print(out)
    return tests.returncode


if __name__ == "__main__":
    raise SystemExit(main())
