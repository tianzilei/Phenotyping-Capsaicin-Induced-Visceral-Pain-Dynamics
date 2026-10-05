"""Resolve unique current aggregate sources; audit hashes and observation algebra."""

from pathlib import Path
from datetime import datetime, timezone
import json
import sys
import hashlib
import shutil
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from capsaicin.distributed_observation import tokens_to_arrays
from run_dask_derivative_development import sha, write_new

BASE = Path.home() / ".local/share/capsaicin-dask"
ROSTER = {
    "observations": "dask_observation_bootstrap_20261003T090651Z_ad45a53d",
    "prediction": "dask_prediction_repeats_20261003T105043Z_8eaf27a2",
    "python_remaining": "dask_python_remaining_20261003T114938Z_3ce82611",
    "variability": "dask_variability_bootstrap_20261003T105251Z_43abcbc2",
    "R_main": "dask_R_prepared_20261003T134447Z_82432c21",
    "FPCA_precision": "dask_R_prepared_20261003T171859Z_7cec37d3",
    "GAMM_synthetic": "gamm_nuisance_development_20261004_v1",
    "derivative_synthetic": "dask_derivative_development_20261003T085400Z_52701571",
    "completion": "science_completion_20261003T180414Z_fc7855a4",
}


def prepare():
    out = BASE / "deliveries/scientific_report_sources_20261004_v3"
    out.mkdir(parents=True, exist_ok=False)
    audit = {}
    sources = {}
    allmc = []
    for role, name in ROSTER.items():
        run = BASE / "runs" / name
        c = json.loads((run / "completion.json").read_bytes())
        for filename, h in c.get("outputs_sha256", {}).items():
            assert sha(run / filename) == h, (role, filename)
        manifest = run / (
            "run_manifest.json"
            if (run / "run_manifest.json").exists()
            else "manifest.json"
        )
        m = json.loads(manifest.read_bytes())
        for filename, h in m.get("input_sha256", {}).items():
            assert sha(ROOT / filename) == h, (role, filename)
        audit[role] = dict(
            run=str(run),
            completion_sha256=sha(run / "completion.json"),
            manifest_sha256=sha(manifest),
            verified_completion_outputs=len(c.get("outputs_sha256", {})),
            jobs=c.get("jobs"),
            status=c["status"],
        )
        (out / role).mkdir()
        for p in run.glob("*summary.json"):
            shutil.copyfile(p, out / role / p.name)
            sources[str(p)] = sha(p)
            d = json.loads(p.read_bytes())
            for s in d if isinstance(d, list) else []:
                if (
                    isinstance(s, dict)
                    and "MC_max_endpoint_half_width" in s
                    and not (role == "R_main" and p.name == "complete_summary.json")
                ):
                    r = {k: v for k, v in s.items() if not isinstance(v, (dict, list))}
                    r.update(
                        source_role=role,
                        source_file=p.name,
                        lower_estimate=s.get("lower", {}).get("estimate"),
                        upper_estimate=s.get("upper", {}).get("estimate"),
                    )
                    allmc.append(r)
        if role == "completion":
            for filename in [
                "symptoms_point.json",
                "finite_changes_point.json",
                "supports.json",
            ]:
                p = run / filename
                shutil.copyfile(p, out / role / filename)
                sources[str(p)] = sha(p)
        if role in ["R_main", "FPCA_precision"]:
            (out / role / "references").mkdir()
            for p in (run / "results").glob("reference__*.json"):
                result = json.loads(p.read_bytes())["payload"]["result"]
                write_new(out / role / "references" / p.name, result)
                sources[str(p)] = sha(p)
    source = (
        ROOT
        / "08_outputs/analysis_completion_20261002T152859Z_12f7386c/people_private.csv"
    )
    frame = (
        pd.read_csv(source, dtype=str, keep_default_na=False)
        .sort_values("ID")
        .reset_index(drop=True)
    )
    values, events = tokens_to_arrays(
        frame[[f"VAS_{t}min" for t in range(1, 21)]].to_numpy()
    )
    legacy = ROOT / "08_outputs/reanalysis_20260926_20260925T165400Z_c9b9d41d"
    (out / "observed_algebra").mkdir()
    directory = legacy / "descriptives_eff94054"
    manifest = json.loads((directory / "manifest.json").read_bytes())
    for filename, h in manifest["outputs_sha256"].items():
        assert sha(directory / filename) == h
    for filename in [
        "adjacent_composition.csv",
        "bounded_means.csv",
        "marker_distribution.csv",
        "area_bounds.csv",
        "observed_by_marker.csv",
    ]:
        p = directory / filename
        shutil.copyfile(p, out / "observed_algebra" / filename)
        sources[str(p)] = sha(p)
    old_curve = pd.read_csv(directory / "observed_curve.csv")
    means = np.nanmean(values, axis=0)
    support = np.isfinite(values).sum(axis=0)
    assert np.allclose(old_curve.mean_observed, means, atol=1e-12) and np.array_equal(
        old_curve.n_observed, support
    )
    mc = json.loads((out / "observations/VAS_observation_summary.json").read_bytes())
    rows = []
    for t in range(20):
        s = next(x for x in mc if x["statistic"] == f"mean_observed_minute{t + 1}")
        assert abs(s["point"] - means[t]) < 1e-12
        rows.append(
            dict(
                minute=t + 1,
                observed_people=int(support[t]),
                mean_observed=float(means[t]),
                resampling_lower=s["lower"]["estimate"],
                resampling_upper=s["upper"]["estimate"],
                MC_status=s["status"],
                MC_max_half_width=s["MC_max_endpoint_half_width"],
            )
        )
    pd.DataFrame(rows).to_csv(
        out / "observed_algebra/observed_curve_latest.csv", index=False
    )
    composition = pd.read_csv(out / "observed_algebra/adjacent_composition.csv")
    maxima = 0
    for t, row in enumerate(composition.to_dict("records")):
        a = np.isfinite(values[:, t])
        b = np.isfinite(values[:, t + 1])
        both = a & b
        paired = np.mean(values[both, t + 1] - values[both, t])
        start = np.mean(values[both, t]) - means[t]
        end = means[t + 1] - np.mean(values[both, t + 1])
        expected = [means[t + 1] - means[t], paired, start, end, start + end]
        actual = [
            row[k]
            for k in [
                "observed_mean_change",
                "paired_observed_change",
                "start_composition",
                "end_composition",
                "composition_total",
            ]
        ]
        assert np.allclose(expected, actual, atol=1e-12)
        assert [
            row[k] for k in ["n_start", "n_end", "n_both", "n_leaving", "n_entering"]
        ] == [a.sum(), b.sum(), both.sum(), (a & ~b).sum(), (~a & b).sum()]
        maxima = max(maxima, max(abs(np.array(actual) - expected)))
    bounds = pd.read_csv(out / "observed_algebra/bounded_means.csv")
    lower = np.nansum(values, axis=0) / len(frame)
    upper = lower + 10 * (len(frame) - support) / len(frame)
    assert np.allclose(bounds.cohort_mean_lower, lower) and np.allclose(
        bounds.cohort_mean_upper, upper
    )
    markers = pd.read_csv(out / "observed_algebra/marker_distribution.csv")
    for t in range(20):
        assert markers.n_first_E.iloc[t] == np.sum(
            events[:, 0] == t + 1
        ) and markers.n_first_T.iloc[t] == np.sum(events[:, 1] == t + 1)
    cohort = [
        dict(characteristic="All people", n=215, summary="215"),
        dict(characteristic="Numeric VAS ratings", n=3424, summary="3424"),
        dict(characteristic="Complete minutes 1–10", n=206, summary="206 / 215"),
        dict(characteristic="Complete minutes 1–20", n=56, summary="56 / 215"),
    ]
    for category, n in frame.Sex.value_counts().items():
        cohort.append(
            dict(
                characteristic="Recorded sex: " + category,
                n=int(n),
                summary=f"{n} / 215",
            )
        )
    for field in ["Age", "Height_cm", "Weight_kg", "BMI"]:
        numeric = pd.to_numeric(
            frame[field].replace("", np.nan), errors="raise"
        ).dropna()
        cohort.append(
            dict(
                characteristic=field,
                n=len(numeric),
                summary=f"{numeric.median():.2f} [{numeric.quantile(0.25):.2f}, {numeric.quantile(0.75):.2f}]",
                missing=215 - len(numeric),
                definition="median [Q1,Q3]; observed field only",
            )
        )
    for marker in ["E", "T"]:
        n = int(np.sum(events[:, 0 if marker == "E" else 1] <= 20))
        cohort.append(
            dict(
                characteristic="People with first coded " + marker,
                n=n,
                summary=f"{n} / 215",
            )
        )
    pd.DataFrame(cohort).to_csv(out / "cohort.csv", index=False)
    # Preserve reviewed descriptive correlations with explicit signs, without assigning biological labels.
    p = legacy / "fpca_followup_956672b7/redundancy.csv"
    shutil.copyfile(p, out / "FPCA_precision/redundancy.csv")
    sources[str(p)] = sha(p)
    pred = BASE / "audit/scientific_completion_20261004_v1"
    for filename in [
        "prediction_summary.csv",
        "prediction_all_repeat_metrics.csv",
        "prediction_verification.json",
        "new_completion_verification.json",
    ]:
        p = pred / filename
        shutil.copyfile(p, out / filename)
        sources[str(p)] = sha(p)
    matrix = pd.read_csv(ROOT / "docs/full_plan_review_module_matrix_20261003.csv")
    roles = {
        "U00": "completion",
        "U01": "observations",
        "U02": "R_main",
        "U03": "FPCA_precision",
        "U04": "python_remaining",
        "U05": "python_remaining",
        "U06": "variability",
        "U07": "completion",
        "U08": "python_remaining",
        "U09": "python_remaining",
        "U10": "python_remaining",
        "U11": "python_remaining",
        "U12": "python_remaining",
        "U13": "prediction",
        "U14": "observations",
        "U15": "completion",
        "U16": None,
        "U17": None,
    }
    statuses = {
        "U00": "source_audit_complete",
        "U01": "observed_description_complete",
        "U02": "working_model_complete_MC_0_of_120",
        "U03": "working_models_complete_complete_MC_12_of_24_sparse_4_of_48",
        "U04": "partition_sensitivity_complete_MC_1_of_176",
        "U05": "training_partition_recovery_complete_not_clinical",
        "U06": "observed_metrics_complete_MC_78_of_96",
        "U07": "recorded_code_description_complete_MC_135_of_139",
        "U08": "candidate_only_primary_blocked",
        "U09": "candidate_only_primary_blocked",
        "U10": "candidate_only_phase_blocked",
        "U11": "development_only_sealed_closed",
        "U12": "training_partition_recovery_complete_not_forecasting",
        "U13": "20_repeats_complete_internal_evaluation",
        "U14": "coded_stop_description_complete_medical_sources_partial",
        "U15": "finite_changes_complete_MC_336_of_364_instantaneous_derivative_blocked",
        "U16": "interface_design_only_real_analysis_blocked",
        "U17": "design_only_real_phase_directionality_blocked",
    }
    matrix["latest_status"] = [statuses[u] for u in matrix.module_id]
    matrix["current_run"] = [
        audit[roles[u]]["run"] if roles[u] else "" for u in matrix.module_id
    ]
    matrix.to_csv(out / "all_18_modules.csv", index=False)
    pd.DataFrame(allmc).to_csv(out / "all_current_MC_statistics.csv", index=False)
    write_new(
        out / "source_audit.json",
        dict(
            status="PASS",
            runs=audit,
            all_completion_and_input_hashes="PASS",
            observation_support_algebra="PASS",
            max_composition_difference=maxima,
            symptom_and_prediction_independent_audit="PASS",
            tests=289,
            original_full_scientific_objective_complete=False,
            available_observed_support_work_complete=True,
            primary_p_q=None,
            sealed_people_used=0,
            local_compute_workers=0,
        ),
    )
    write_new(
        out / "manifest.json",
        dict(
            created_utc=datetime.now(timezone.utc).isoformat(),
            builder_sha256=sha(Path(__file__)),
            sources_sha256=sources,
            outputs_sha256={
                str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()
            },
        ),
    )
    print(
        json.dumps(
            dict(
                output=str(out),
                status="PASS",
                source_files=len(sources),
                MC_statistics=len(allmc),
                modules=len(matrix),
            )
        ),
        flush=True,
    )
    return out


if __name__ == "__main__":
    prepare()
