"""Export aggregate MC and nuisance diagnostics from verified followup runs."""

import argparse
import json
from pathlib import Path
import sys
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts")]
from run_dask_derivative_development import write_new, sha


def export(run, audit, diagnostics, output, synthetic_audit=None):
    if output.resolve().is_relative_to(ROOT):
        raise ValueError("Use a new Git-external directory")
    verified = json.loads(audit.read_bytes())
    if (
        verified["status"] != "COMPLETED_QUEUE_VERIFIED"
        or Path(verified["run_directory"]) != run
    ):
        raise ValueError("Full verified run required")
    completion = json.loads((run / "completion.json").read_bytes())
    for name, h in completion["outputs_sha256"].items():
        if sha(run / name) != h:
            raise ValueError("Completion artifact changed")
    dc = json.loads((diagnostics / "completion.json").read_bytes())
    if not dc["reference_refits"] or not dc["pilot_preserved"]:
        raise ValueError("Reference diagnostics incomplete")
    for name, h in dc["outputs_sha256"].items():
        if sha(diagnostics / name) != h:
            raise ValueError("Diagnostic artifact changed")
    output.mkdir(parents=True, exist_ok=False)
    frozen = json.loads((run / "run_manifest.json").read_bytes())
    config = frozen["config"]
    mc = []
    for r in json.loads((run / "complete_summary.json").read_bytes()):
        row = {
            k: r[k]
            for k in [
                "cell",
                "metric",
                "index",
                "attempted",
                "valid",
                "failed",
                "status",
                "publication",
                "empirical_range_width",
                "MC_max_endpoint_half_width",
                "gamma_per_endpoint",
            ]
        }
        absolute = 0.5 if r["metric"] == "angle_deg" else 0.002
        row["target_half_width"] = min(
            config["MC"]["relative_tolerance"] * r["empirical_range_width"], absolute
        )
        row["MC_to_target_ratio"] = (
            r["MC_max_endpoint_half_width"] / row["target_half_width"]
        )
        for side in ["lower", "upper"]:
            row.update({side + "_" + k: v for k, v in r[side].items()})
        mc.append(row)
    d = pd.DataFrame(mc)
    d.to_csv(output / "complete_MC_endpoint_precision.csv", index=False)
    pilot = pd.read_csv(diagnostics / "MC_budget_planning.csv")
    pilot = pilot[pilot.stage == "complete"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8), layout="constrained")
    for ax, cid in zip(axes, ["F10", "F20"]):
        q = d[d.cell == cid].reset_index(drop=True)
        old = pilot[pilot.cell == cid].set_index(["metric", "index"])
        ratios = [old.loc[(r.metric, r["index"]), "ratio"] for _, r in q.iterrows()]
        x = np.arange(len(q))
        ax.plot(x, ratios, "o-", label="Old independent run: B=5,000", color="#777777")
        ax.plot(
            x,
            q.MC_to_target_ratio,
            "o-",
            label="New independent run: B=100,000",
            color="#286ca4",
        )
        ax.axhline(
            1, color="#a83e3e", linestyle="--", label="Both MC targets met at ratio ≤ 1"
        )
        ax.set(
            yscale="log",
            xticks=x,
            xticklabels=[
                f"{r.metric.replace('cumulative_fve', 'FVE').replace('angle_deg', 'Angle').replace('matched_inner', 'Inner')} {r['index']}"
                for _, r in q.iterrows()
            ],
            ylabel="Maximum endpoint MC half-width / required half-width",
            title=f"{cid[1:]}-minute complete cohort: {sum(q.status == 'MC_PRECISION_MET')}/12 met",
        )
        ax.tick_params(axis="x", rotation=65)
        ax.grid(axis="y", alpha=0.2)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, fontsize=9)
    fig.suptitle(
        "FPCA Monte Carlo precision: separate runs, unchanged targets\nMC uncertainty only; no population coverage or physiological validation",
        fontsize=12,
    )
    for suffix in ["png", "pdf", "svg"]:
        fig.savefig(output / ("FPCA_MC_precision." + suffix), dpi=180)
    plt.close(fig)
    ref = []
    for f in sorted(diagnostics.glob("reference_diagnostics__*.json")):
        r = json.loads(f.read_bytes())["result"]
        vc = dict(zip(r["VarCorr_rows"], r["VarCorr_values"]))
        ref.append(
            dict(
                cell=f.stem.replace("reference_diagnostics__", ""),
                status=r["status"],
                rho=r["rho"],
                random_intercept_variance=float(vc["(Intercept)"][0]),
                residual_variance=float(vc["Residual"][0]),
                apVar_finite_matrix=r["apVar_finite_matrix"],
                apVar_positive_definite=r["apVar_positive_definite"],
                apVar_message=r["apVar_message"],
                apVar_covariance_condition_number=r[
                    "apVar_covariance_condition_number"
                ],
                Hessian_recomputed=False,
                optimizer_exit_code_available=False,
            )
        )
    pd.DataFrame(ref).to_csv(
        output / "GAMM_reference_nuisance_diagnostics.csv", index=False
    )
    if synthetic_audit:
        synthetic = json.loads(synthetic_audit.read_bytes())
        if synthetic["status"] != "SYNTHETIC_DEVELOPMENT_CHECKPOINTS_VERIFIED":
            raise ValueError("Synthetic audit incomplete")
        pd.DataFrame(synthetic["summary"]).to_csv(
            output / "synthetic_nuisance_summary.csv", index=False
        )
    for name in [
        "GAMM_conditional_curves.csv",
        "GAMM_conditional_diagnostics.json",
        "MC_budget_planning.csv",
        "reference_comparison.json",
    ]:
        (output / name).write_bytes((diagnostics / name).read_bytes())
    (output / "FIGURE_NOTES.md").write_text(
        "The MC plot compares two independent fixed runs, never pooled. The denominator is min(0.02 * empirical range width, absolute target), not the statistic value. A ratio ≤ 1 meets both targets. Old results remain unchanged. The plot does not establish bootstrap population coverage. GAMM apVar-conditioned curves are post-fit descriptive groups; no exclusion or causal interpretation. apVar eigenvalues describe an approximate covariance, not a Hessian.\n",
        encoding="utf-8",
    )
    write_new(
        output / "delivery_manifest.json",
        dict(
            run_directory=str(run),
            verification_sha256=sha(audit),
            reference_diagnostics_directory=str(diagnostics),
            report_script_sha256=sha(Path(__file__)),
            synthetic_audit_sha256=sha(synthetic_audit) if synthetic_audit else None,
            outputs_sha256={p.name: sha(p) for p in output.iterdir() if p.is_file()},
            primary_p_q=None,
        ),
    )
    print(
        json.dumps(
            dict(
                output=str(output),
                MC_met=int(sum(d.status == "MC_PRECISION_MET")),
                MC_total=len(d),
            )
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--diagnostics", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--synthetic-audit", type=Path)
    a = p.parse_args()
    export(
        a.run.resolve(),
        a.audit.resolve(),
        a.diagnostics.resolve(),
        a.output.resolve(),
        a.synthetic_audit,
    )
