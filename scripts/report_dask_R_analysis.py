"""Export aggregate tables and figures from a verified, completed R run."""

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_dask_derivative_development import sha, write_new


def table(path, rows):
    with path.open("x", encoding="utf-8", newline="") as h:
        writer = csv.DictWriter(h, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def export(run, verification, output):
    if output.is_relative_to(ROOT):
        raise ValueError("Results must stay outside the repository")
    audit = json.loads(verification.read_bytes())
    if (
        audit["status"] != "COMPLETED_QUEUE_VERIFIED"
        or Path(audit["run_directory"]) != run
    ):
        raise ValueError("A verified completed run is required")
    completion = json.loads((run / "completion.json").read_bytes())
    for name, h in completion["outputs_sha256"].items():
        if sha(run / name) != h:
            raise ValueError("Output changed since completion")
    frozen = json.loads((run / "run_manifest.json").read_bytes())
    config = frozen["config"]
    output.mkdir(parents=True, exist_ok=False)
    summaries = {
        s: json.loads((run / (s + "_summary.json")).read_bytes())
        for s in ["gamm", "complete", "sparse", "reconstruction"]
    }
    references = {
        p["payload"]["job"]["cell"]["id"]: p["payload"]["result"]
        for p in [
            json.loads(f.read_bytes())
            for f in (run / "results").glob("reference__*.json")
        ]
    }
    mc = []
    for stage in ["gamm", "complete", "sparse"]:
        for r in summaries[stage]:
            row = {
                k: r.get(k)
                for k in [
                    "cell",
                    "metric",
                    "index",
                    "attempted",
                    "valid",
                    "failed",
                    "publication",
                    "status",
                    "empirical_range_width",
                    "MC_max_endpoint_half_width",
                    "gamma_per_endpoint",
                ]
            }
            row["stage"] = stage
            for side in ["lower", "upper"]:
                for key in [
                    "estimate",
                    "lower_MC",
                    "upper_MC",
                    "lower_rank",
                    "upper_rank",
                    "MC_half_width",
                ]:
                    row[side + "_" + key] = (r.get(side) or {}).get(key)
            mc.append(row)
    table(output / "MC_endpoint_precision.csv", mc)
    diagnostics = []
    for c in audit["cells"]:
        if c["stage"] != "gamm":
            continue
        d = references[c["cell"]]["diagnostics"]
        row = dict(
            cell=c["cell"],
            people=d["n_people"],
            observations=d["n_observations"],
            rho=d["rho"],
            reference_apVar_ok=d["apVar_ok"],
            reference_adjacent_residual_correlation=d["residual_adjacent_correlation"],
            actual_adjacent_pairs=d["residual_adjacent_pairs"],
            edf=d["edf"],
            bootstrap_attempted=c["attempted"],
            bootstrap_failed=c["failed"],
            bootstrap_apVar_failed=c["apVar_failed"],
            bootstrap_correlation_boundary=c["correlation_boundary"],
            bootstrap_out_of_scale_fits=c["out_of_scale_fits"],
            MC_met=c["MC_precision_met"],
            MC_total=c["MC_statistics"],
        )
        diagnostics.append(row)
    table(output / "GAMM_diagnostics.csv", diagnostics)
    spectra = []
    for cid, r in sorted(references.items()):
        if cid.startswith("G"):
            continue
        values = np.cumsum(r["fve"]) if cid.startswith("F") else r["cumulative_fve"]
        for k, fve in enumerate(values, 1):
            spectra.append(
                dict(
                    cell=cid,
                    component=k,
                    cumulative_fve=fve,
                    eigenvalue=r["eigenvalue"][k - 1],
                    target="raw_complete_curve_covariance"
                    if cid.startswith("F")
                    else "smoothed_sparse_working_covariance",
                )
            )
    table(output / "FPCA_reference_spectra.csv", spectra)
    cv = []
    for cell in summaries["reconstruction"]:
        for r in cell["complete_repeats"]:
            for k in range(5):
                cv.append(
                    dict(
                        cell=cell["cell"],
                        repeat=r["repeat"],
                        components=k,
                        mean_person_rmse=r["mean_rmse"][k],
                        person_constant_rmse=r["person_constant_rmse"],
                        paired_difference=r["paired_difference"][k],
                        role="retrospective_full_curve_reconstruction_split_sensitivity",
                    )
                )
    if cv:
        table(output / "reconstruction_repeat_summary.csv", cv)
    curves = []
    for cid, r in sorted(references.items()):
        if not cid.startswith("G"):
            continue
        for minute, estimate in enumerate(r["curve"], 1):
            s = next(
                x
                for x in summaries["gamm"]
                if x["cell"] == cid and x["index"] == minute
            )
            curves.append(
                dict(
                    cell=cid,
                    minute=minute,
                    working_model_curve=estimate,
                    empirical_observed_mean=r["empirical_mean"][minute - 1],
                    successful_fit_range_lower=(s.get("lower") or {}).get("estimate"),
                    successful_fit_range_upper=(s.get("upper") or {}).get("estimate"),
                    MC_status=s["status"],
                    publication=s["publication"],
                )
            )
    table(output / "GAMM_curves.csv", curves)
    plt.rcParams.update(
        {"font.size": 10, "axes.spines.top": False, "axes.spines.right": False}
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), constrained_layout=True)
    gamm_met = sum(r["status"] == "MC_PRECISION_MET" for r in summaries["gamm"])
    fig.suptitle(
        f"Exploratory; MC precision met: {gamm_met}/{len(summaries['gamm'])} statistics",
        fontsize=11,
    )
    for ax, end in zip(axes, [10, 20]):
        main = "G10_common_k6" if end == 10 else "G20_primary_k6"
        labels = {
            "G10_common_k6": "Observed, CAR1 k6",
            "G10_complete_k6": "Complete, CAR1 k6",
            "G20_primary_k6": "Observed, CAR1 k6",
            "G20_independent_k6": "Observed, independent k6",
            "G20_k4": "Observed, CAR1 k4",
            "G20_k8": "Observed, CAR1 k8",
            "G20_complete_k6": "Complete, CAR1 k6",
        }
        selected = [c for c in config["gamm"]["cells"] if c["end"] == end]
        for c in selected:
            cid = c["id"]
            x = np.arange(1, end + 1)
            ax.plot(x, references[cid]["curve"], label=labels[cid], lw=1.7)
            if cid == main:
                rows = [r for r in curves if r["cell"] == cid]
                if all(r["successful_fit_range_lower"] is not None for r in rows):
                    ax.fill_between(
                        x,
                        [r["successful_fit_range_lower"] for r in rows],
                        [r["successful_fit_range_upper"] for r in rows],
                        alpha=0.15,
                        color="C0",
                    )
        ax.plot(
            np.arange(1, end + 1),
            references[main]["empirical_mean"],
            color="black",
            ls=":",
            label="Actually observed mean",
        )
        ax.set(
            xlabel="Actual minute",
            ylabel="VAS",
            title=f"1–{end} minutes: working-model curves",
        )
        ax.legend(fontsize=8, frameon=False)
    for suffix in ["png", "pdf", "svg"]:
        fig.savefig(output / ("GAMM_curves." + suffix), dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.1), constrained_layout=True)
    for ax, cell in zip(axes, summaries["reconstruction"]):
        for r in cell["complete_repeats"]:
            ax.plot(range(5), r["paired_difference"], alpha=0.2, color="C0", lw=0.8)
        if cell["complete_repeats"]:
            values = np.asarray(
                [r["paired_difference"] for r in cell["complete_repeats"]]
            )
            ax.plot(
                range(5),
                np.median(values, axis=0),
                color="C0",
                marker="o",
                label="Median across repeats",
            )
        ax.axhline(0, color="grey", lw=0.8)
        ax.set(
            xlabel="FPCA components",
            ylabel="Mean paired RMSE difference (VAS)",
            xticks=range(5),
            title=f"{cell['cell']}: {len(cell['complete_repeats'])} complete split repeats",
        )
        ax.legend(frameon=False, fontsize=8)
    for suffix in ["png", "pdf", "svg"]:
        fig.savefig(output / ("reconstruction_split_sensitivity." + suffix), dpi=180)
    plt.close(fig)
    with (output / "FIGURE_NOTES.md").open("x", encoding="utf-8") as h:
        h.write(
            "# 图表解释范围\n\nGAMM曲线阴影是主观察人群设定的成功拟合条件2.5%–97.5%重抽范围，非校准人口置信带、导数带或缺失后反事实均值。实际观察均值的风险集随分钟改变。MC精度、apVar、失败和不同完整者人群见CSV。\n\n重建图每条细线为一次整人划分的平均配对RMSE差，粗线为20次划分中的中位数；基线是同一测试者完整曲线的加权个人常数。完整测试曲线用于投影，不是未来预测；重复划分不是独立人群或显著性检验。负差表示该次划分下相对个人常数的重建RMSE较低。\n\n完整FPCA原评分协方差和稀疏FPCA平滑工作协方差的解释率对应不同目标，不能作为性能优劣的直接比较。\n"
        )
    summary = dict(
        status="verified_completed_frozen_R_queue",
        created_utc=datetime.now(timezone.utc).isoformat(),
        run_directory=str(run),
        run_manifest_sha256=sha(run / "run_manifest.json"),
        completion_sha256=sha(run / "completion.json"),
        verification_sha256=sha(verification),
        reporter_sha256=sha(Path(__file__)),
        git_revision=frozen["git_revision"],
        jobs=completion["jobs"],
        MC={
            s: dict(
                met=sum(r["status"] == "MC_PRECISION_MET" for r in summaries[s]),
                total=len(summaries[s]),
            )
            for s in ["gamm", "complete", "sparse"]
        },
        cells=audit["cells"],
        reconstruction={
            c["cell"]: dict(
                complete_repeats=len(c["complete_repeats"]),
                failed_or_incomplete_repeats=c["failed_or_incomplete_repeats"],
            )
            for c in summaries["reconstruction"]
        },
        primary_p_q=None,
        sealed_people_used=0,
        outputs_sha256={p.name: sha(p) for p in output.iterdir() if p.is_file()},
    )
    write_new(output / "delivery_manifest.json", summary)
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--verification", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    r = export(a.run.resolve(), a.verification.resolve(), a.output.resolve())
    print(
        json.dumps(
            dict(output=str(a.output), jobs=r["jobs"], MC=r["MC"]), ensure_ascii=False
        )
    )
