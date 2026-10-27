"""Explicit-source, post-hoc physiology extension. No raw or prior output changes."""

from pathlib import Path
import sys
import json
import hashlib
import datetime
import importlib.util
import importlib.metadata
import subprocess
import warnings

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime import locations, start_run, require_missing

ROOT, OUT, CFG, CONFIG_PATH = locations("extension")
PRIOR = ROOT / CFG["prior_run"]
sp = importlib.util.spec_from_file_location(
    "prior_inference", Path(__file__).with_name("analyse.py")
)
prior = importlib.util.module_from_spec(sp)
sp.loader.exec_module(prior)
S = {k: ROOT / v for k, v in CFG["sources"].items() if not Path(v).is_absolute()}
INPUTS = {}
FAILURES = []
MODELS = []
INDEPENDENT = []


def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(p, inherited=True, **kw):
    p = Path(p)
    INPUTS[str(p)] = sha(p)
    if inherited:
        matches = []
        for name in ["manifest.json", "run_manifest.json"]:
            m = p.parent / name
            if m.exists():
                meta = json.loads(m.read_text(encoding="utf-8-sig"))
                for field in ["outputs_sha256", "output_sha256"]:
                    for key, val in meta.get(field, {}).items():
                        if key.replace("\\", "/").split("/")[-1] == p.name:
                            matches.append(val)
        if not matches or any(x != INPUTS[str(p)] for x in matches):
            raise ValueError("missing/mismatched inherited hash: " + str(p))
    return pd.read_csv(p, encoding="utf-8-sig", **kw)


def save(name, data):
    pd.DataFrame(data).to_csv(OUT / name, index=False, mode="x")


def keep_people(d, columns, minimum=2):
    d = d[np.isfinite(d[columns]).all(axis=1)].copy()
    n = d.groupby("person_id").block.nunique()
    return (
        d[d.person_id.isin(n[n >= minimum].index)]
        .sort_values(["person_id", "block"])
        .reset_index(drop=True)
    )


def standardize(d, source="value", target="value"):
    d = d.copy()
    mu = d.groupby("person_id")[source].transform("mean")
    sd = d.groupby("person_id")[source].transform("std")
    d[target] = (d[source] - mu) / sd
    return keep_people(d, [target])


def full_design_check(p, r):
    """Independent full-FE CR1 and identity-working-model CR2/Satterthwaite."""
    d = p["d"]
    slope_cols = ["vas_mean"] + (
        ["HR"] if "HR" in d.columns and p["K"] == len(pd.unique(d.block)) + 1 else []
    )
    # Predictor list supplied separately, not inferred from a test result.
    slope_cols = d.attrs["predictors"]
    D = np.column_stack(
        [
            d[slope_cols].to_numpy(),
            pd.get_dummies(
                d.block.astype(int), drop_first=True, dtype=float
            ).to_numpy(),
            pd.get_dummies(d.person_id, dtype=float).to_numpy(),
        ]
    )
    y = d.value.to_numpy()
    bread = np.linalg.inv(np.einsum("ni,nj->ij", D, D))
    beta = np.einsum("ij,nj,n->i", bread, D, y, optimize=False)
    u = y - np.einsum("ni,i->n", D, beta)
    H = np.einsum("ni,ij,mj->nm", D, bread, D, optimize=False)
    s1, s2, vectors = [], [], []
    for g in range(p["G"]):
        ix = np.flatnonzero(p["g"] == g)
        Xg = D[ix]
        s1.append(np.einsum("ni,n->i", Xg, u[ix]))
        Rg = np.eye(len(ix)) - H[np.ix_(ix, ix)]
        eig, V = np.linalg.eigh((Rg + Rg.T) / 2)
        if eig.min() < -1e-8:
            raise ValueError("negative CR2 residual covariance")
        invsqrt = np.zeros_like(eig)
        invsqrt[eig > 1e-10] = 1 / np.sqrt(eig[eig > 1e-10])
        A = np.einsum("ij,j,kj->ik", V, invsqrt, V)
        s2.append(np.einsum("ni,nm,m->i", Xg, A, u[ix]))
        w = np.einsum("nm,mi,i->n", A, Xg, bread[:, 0])
        a = np.zeros(len(d))
        a[ix] = w
        vectors.append(a - np.einsum("nm,m->n", H, a))
    se1 = np.sqrt(
        r["correction"] * sum(np.einsum("i,i->", bread[0], s) ** 2 for s in s1)
    )
    se2 = np.sqrt(sum(np.einsum("i,i->", bread[0], s) ** 2 for s in s2))
    Vectors = np.asarray(vectors)
    gram = np.einsum("in,jn->ij", Vectors, Vectors)
    df2 = np.trace(gram) ** 2 / np.sum(gram**2)
    ci = stats.t.ppf(0.975, df2) * se2
    assert abs(beta[0] - r["b"][0]) < 1e-8
    assert abs(se1 - r["se"][0]) < 1e-8
    return dict(
        explicit_FE_beta=beta[0],
        explicit_FE_CR1_se=se1,
        beta_abs_difference=abs(beta[0] - r["b"][0]),
        CR1_se_abs_difference=abs(se1 - r["se"][0]),
        se_CR2_python=se2,
        df_CR2_python=df2,
        p_CR2_python=2 * stats.t.sf(abs(beta[0] / se2), df2),
        ci95_CR2_python_low=beta[0] - ci,
        ci95_CR2_python_high=beta[0] + ci,
    )


def estimate(d, xs=("vas_mean",), full=False, loo=True):
    d = keep_people(d, ["value"] + list(xs))
    p = prior.prepare(d, "value", list(xs))
    p["d"].attrs["predictors"] = list(xs)
    r = prior.fit(p, include_loo=loo)
    if loo:
        row = prior.row_of(p, r)
    else:
        row = dict(
            n_people=p["G"],
            n_blocks=p["N"],
            beta=r["b"][0],
            se_CR1=r["se"][0],
            ci95_low=r["low"][0],
            ci95_high=r["high"][0],
            p_CR1=r["p"][0],
            df=r["df"],
        )
    row["residual_score_ss"] = float(np.sum(p["X"][:, 0] ** 2))
    if full:
        row.update(full_design_check(p, r))
    return row, p


def raw_path(text):
    s = str(text).replace("\\", "/")
    if s.startswith(str(ROOT) + "/"):
        return Path(s)
    if "/capsaicin_analysis_2026-09-13/" in s:
        return ROOT / s.split("/capsaicin_analysis_2026-09-13/", 1)[1]
    return Path(s)


def inventory(nominal):
    rows = []
    for kind, key in [("official_Hb", "hb"), ("ACQ_channels", "ecg_egg")]:
        d = read(S[key] / "record_audit_private.csv")
        paths = [raw_path(x) for x in d.path.unique()]
        exists = [x for x in paths if x.is_file()]
        rows.append(
            dict(
                resource=kind,
                records=len(d),
                people=d.person_id.nunique(),
                unique_source_files=len(paths),
                source_files_present=len(exists),
                min_sampling_hz=d.sampling_hz.min(),
                max_sampling_hz=d.sampling_hz.max(),
            )
        )
    for (roi, metric), d in nominal.groupby(["roi", "metric"]):
        rows.append(
            dict(
                resource="eligible_nominal_" + roi + "_" + metric,
                records=len(d),
                people=d.person_id.nunique(),
            )
        )
    peaks = sorted(S["ecg_egg"].glob("*_peaks_private.npz"))
    rows.append(dict(resource="stored_peak_archives", records=len(peaks)))
    validation = S["validation"] / "summary.json"
    INPUTS[str(validation)] = sha(validation)
    meta = json.loads(validation.read_text())
    (OUT / "reference_status.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2)
    )
    save("data_availability.csv", rows)


def scenario_data():
    cols = [
        "person_id",
        "block",
        "support_spec",
        "minutes",
        "offset_s",
        "drift_ppm",
        "mad",
        "guard_s",
        "coverage_threshold",
        "roi_fraction",
        "roi",
        "metric",
        "value",
        "vas_mean",
        "algorithm_candidate_pass",
    ]
    hp = S["hb"] / "features_private.csv"
    INPUTS[str(hp)] = sha(hp)
    m = json.loads((hp.parent / "manifest.json").read_text())
    assert m["outputs_sha256"][hp.name] == INPUTS[str(hp)]
    parts = []
    for c in pd.read_csv(hp, usecols=cols, chunksize=150000):
        parts.append(
            c[
                (c.mad == 6)
                & (c.guard_s == 2)
                & (c.coverage_threshold == 0.9)
                & (c.roi_fraction == 0.5)
                & c.algorithm_candidate_pass.astype(str).str.lower().eq("true")
            ]
        )
    h = pd.concat(parts, ignore_index=True)
    e = read(S["ecg_egg"] / "features_private.csv", low_memory=False)
    e = e[
        e.metric.isin(["HR", "candidate_RR_RMSSD"])
        & e.algorithm_candidate_pass.astype(str).str.lower().eq("true")
    ].copy()
    e["roi"] = "ECG"
    return h, e


def fixed_support(h, e):
    results = []
    support = []
    for kind, frame in [("Hb", h), ("ECG", e)]:
        for (roi, metric), allrows in frame.groupby(["roi", "metric"], sort=True):
            base = allrows[
                (allrows.support_spec == "A")
                & (allrows.offset_s == 0)
                & (allrows.drift_ppm == 0)
            ].copy()
            base = keep_people(base, ["value", "vas_mean"])
            standardized = standardize(base) if kind == "Hb" else base
            original, _ = estimate(standardized, loo=False)
            for (spec, offset, drift), scenario in allrows.groupby(
                ["support_spec", "offset_s", "drift_ppm"]
            ):
                key = dict(
                    roi=roi,
                    metric=metric,
                    support_spec=spec,
                    offset_s=offset,
                    drift_ppm=drift,
                )
                try:
                    joint = base.merge(
                        scenario,
                        on=["person_id", "block"],
                        suffixes=("_n", "_s"),
                        validate="one_to_one",
                    )
                    same = np.isclose(
                        joint.vas_mean_n, joint.vas_mean_s, atol=1e-12
                    ) & joint.minutes_n.eq(joint.minutes_s)
                    mismatch = int((~same).sum())
                    joint = joint[same].copy()
                    joint = keep_people(joint, ["value_n", "value_s", "vas_mean_n"])
                    if kind == "Hb":
                        mu = joint.groupby("person_id").value_n.transform("mean")
                        sd = joint.groupby("person_id").value_n.transform("std")
                        joint["yn"] = (joint.value_n - mu) / sd
                        joint["ys"] = (joint.value_s - mu) / sd
                    else:
                        joint["yn"] = joint.value_n
                        joint["ys"] = joint.value_s
                    joint = keep_people(joint, ["yn", "ys"])
                    data = joint[["person_id", "block"]].copy()
                    data["vas_mean"] = joint.vas_mean_n
                    data["value"] = joint.yn
                    restricted, _ = estimate(data, loo=False)
                    data["value"] = joint.ys
                    shifted, _ = estimate(data, loo=False)
                    ids = "|".join(
                        joint.person_id.astype(str)
                        + "@"
                        + joint.block.astype(str)
                        + "@"
                        + joint.minutes_n.astype(str)
                    )
                    results.append(
                        dict(
                            **key,
                            status="estimated",
                            mismatched_score_or_minutes_rows=mismatch,
                            original_people=original["n_people"],
                            original_blocks=original["n_blocks"],
                            common_people=restricted["n_people"],
                            common_blocks=restricted["n_blocks"],
                            beta_nominal_original=original["beta"],
                            beta_nominal_common=restricted["beta"],
                            beta_shifted_common=shifted["beta"],
                            delta_restriction_scale=restricted["beta"]
                            - original["beta"],
                            delta_timing_fixed_scale=shifted["beta"]
                            - restricted["beta"],
                            ci95_nominal_common_low=restricted["ci95_low"],
                            ci95_nominal_common_high=restricted["ci95_high"],
                            ci95_shifted_common_low=shifted["ci95_low"],
                            ci95_shifted_common_high=shifted["ci95_high"],
                            support_sha256=hashlib.sha256(ids.encode()).hexdigest(),
                        )
                    )
                    for block, b in joint.groupby("block"):
                        support.append(
                            dict(
                                **key,
                                block=block,
                                n_people=b.person_id.nunique(),
                                n_blocks=len(b),
                            )
                        )
                except (ValueError, np.linalg.LinAlgError, AssertionError) as err:
                    results.append(dict(**key, status="not_estimable", reason=str(err)))
    save("fixed_support_timing.csv", results)
    save("fixed_support_block_coverage.csv", support)
    return results


def main():
    nominal = read(S["associations"] / "model_input_private.csv")
    people = read(S["person_run"] / "BaselineData_person_private.csv", inherited=False)
    assert (
        len(people) == 215
        and people.ID.is_unique
        and set(nominal.person_id) <= set(people.ID)
    )
    inventory(nominal)
    h, e = scenario_data()
    assert set(h.person_id) | set(e.person_id) <= set(people.ID)
    raw = h[(h.support_spec == "A") & (h.offset_s == 0) & (h.drift_ppm == 0)].copy()
    raw.to_csv(OUT / "nominal_raw_Hb_private.csv", index=False)
    print("Data and inherited hashes verified; starting core models", flush=True)
    roster = pd.read_csv(OUT / "planned_core_tests_54.csv")
    results = []
    comparisons = []
    common_diag = []
    HR = nominal[(nominal.roi == "ECG") & (nominal.metric == "HR")][
        ["person_id", "block", "value", "vas_mean"]
    ].rename(columns={"value": "HR", "vas_mean": "hr_score"})
    for test in roster.to_dict("records"):
        tid, family, metric, roi = (
            test["test_id"],
            test["family"],
            test["outcome"],
            test["region"],
        )
        record = dict(test_id=tid, family=family, roi=roi, metric=metric)
        try:
            xs = ["vas_mean"]
            if family == "C1_original24":
                d = nominal[(nominal.roi == roi) & (nominal.metric == metric)].copy()
            elif family == "C2_bilateral8":
                base_roi = roi.replace("_L_minus_R", "")
                left = raw[(raw.roi == base_roi + "_L") & (raw.metric == metric)]
                right = raw[(raw.roi == base_roi + "_R") & (raw.metric == metric)]
                z = left.merge(
                    right,
                    on=["person_id", "block"],
                    suffixes=("_L", "_R"),
                    validate="one_to_one",
                )
                assert np.allclose(z.vas_mean_L, z.vas_mean_R)
                z = keep_people(z, ["value_L", "value_R"])
                for side in ["L", "R"]:
                    z = standardize(z, "value_" + side, "z_" + side)
                d = z[["person_id", "block"]].copy()
                d["value"] = z.z_L - z.z_R
                d["vas_mean"] = z.vas_mean_L
            else:
                d = nominal[(nominal.roi == roi) & (nominal.metric == metric)].merge(
                    HR, on=["person_id", "block"], validate="one_to_one"
                )
                assert np.allclose(d.vas_mean, d.hr_score)
                d = keep_people(d, ["value", "vas_mean", "HR"])
                plain, _ = estimate(d)
                xs = ["vas_mean", "HR"]
                # Both models share rows AND inherited fixed Hb scale.
                comparisons.append(
                    dict(
                        test_id=tid,
                        roi=roi,
                        metric=metric,
                        model="same_rows_no_HR",
                        **plain,
                    )
                )
            value, p = estimate(d, xs, full=True)
            record.update(status="estimated", **value)
            temp = p["d"][
                ["person_id", "block", "value", "vas_mean"]
                + (["HR"] if len(xs) == 2 else [])
            ].copy()
            temp["test_id"] = tid
            temp["has_HR"] = len(xs) == 2
            MODELS.append(temp)
            INDEPENDENT.append(
                dict(
                    test_id=tid,
                    **{
                        k: v
                        for k, v in value.items()
                        if "python" in k
                        or "difference" in k
                        or k.startswith("explicit_")
                    },
                )
            )
            if family == "C3_HR_conditioned22":
                newscale = standardize(d)
                sr, _ = estimate(newscale, xs)
                comparisons.append(
                    dict(
                        test_id=tid,
                        roi=roi,
                        metric=metric,
                        model="same_rows_HR_common_support_SD",
                        **sr,
                    )
                )
        except (ValueError, np.linalg.LinAlgError, AssertionError) as err:
            record.update(status="not_estimable", reason=str(err))
            FAILURES.append(record.copy())
        results.append(record)
        print(tid, record["status"], flush=True)
    result = pd.DataFrame(results)
    assert len(result) == 54
    for family, idx in result.groupby("family").groups.items():
        assert len(idx) == CFG["families"][family]
        for method in ["BY", "BH"]:
            result.loc[idx, "q_" + method + "_family"] = prior.adjust(
                result.loc[idx, "p_CR1"], method
            )
    for method in ["BY", "BH"]:
        result["q_" + method + "_global54"] = prior.adjust(result.p_CR1, method)
        result["q_CR3_" + method + "_global54"] = prior.adjust(result.p_CR3, method)
    save("core_54_results.csv", result)
    save("HR_same_rows_comparisons.csv", comparisons)
    save("independent_full_FE_checks.csv", INDEPENDENT)
    pd.concat(MODELS, ignore_index=True).to_csv(
        OUT / "core_model_inputs_private.csv", index=False
    )
    old = pd.read_csv(PRIOR / "all_161_results.csv")
    checks = result[result.family == "C1_original24"].merge(
        old[old.family == "VAS_features"],
        on=["roi", "metric"],
        suffixes=("_new", "_old"),
    )
    assert len(checks) == 24
    for col in ["beta", "se_CR1", "ci95_low", "ci95_high", "p_CR1"]:
        assert np.allclose(checks[col + "_new"], checks[col + "_old"], atol=1e-9), col
    save(
        "original24_reproduction.csv",
        checks[
            [
                "test_id",
                "roi",
                "metric",
                "beta_new",
                "beta_old",
                "se_CR1_new",
                "se_CR1_old",
            ]
        ],
    )
    print(
        "Core 54 and independent full-FE checks completed; fixed-support comparisons",
        flush=True,
    )
    timing = fixed_support(h, e)
    # Measured-region component diagnostics: all 11 ROIs, leave target out.
    nominal_hb = nominal[nominal.roi != "ECG"]
    regions = sorted(nominal_hb.roi.unique())
    assert len(regions) == 11
    for metric in ["HbO", "HbR"]:
        wide = (
            nominal_hb[nominal_hb.metric == metric]
            .pivot(
                index=["person_id", "block", "vas_mean"], columns="roi", values="value"
            )
            .dropna()
            .reset_index()
        )
        wide = keep_people(wide, regions)
        # Re-standardize each region ON THE SAME fixed all-ROI support.
        for region in regions:
            wide = standardize(wide, region, region)
        for region in regions:
            d = wide[["person_id", "block", "vas_mean"]].copy()
            d["value"] = wide[region]
            d["common_Hb"] = wide[[x for x in regions if x != region]].mean(axis=1)
            try:
                plain, _ = estimate(d)
                conditional, _ = estimate(d, ["vas_mean", "common_Hb"])
                common_diag.append(
                    dict(
                        roi=region,
                        metric=metric,
                        model="same_allROI_rows_no_component",
                        role="descriptive_not_discovery",
                        **plain,
                    )
                )
                common_diag.append(
                    dict(
                        roi=region,
                        metric=metric,
                        model="same_allROI_rows_other10_mean",
                        role="descriptive_not_discovery",
                        **conditional,
                    )
                )
            except (ValueError, np.linalg.LinAlgError) as err:
                common_diag.append(
                    dict(
                        roi=region,
                        metric=metric,
                        status="not_estimable",
                        reason=str(err),
                    )
                )
    # Drop p values: these are predesignated diagnostic coefficients, not discovery screens.
    cd = pd.DataFrame(common_diag).drop(columns=["p_CR1", "p_CR3"], errors="ignore")
    save("shared_measured_component_diagnostic.csv", cd)
    save("failures.csv", FAILURES or [dict(stage="core", failures=0)])
    env = {x: importlib.metadata.version(x) for x in ["numpy", "pandas", "scipy"]}
    manifest = dict(
        status="core_and_fixed_support_completed_R_CR2_check_pending",
        utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        configuration_sha256=sha(OUT / "frozen_config.json"),
        code_sha256=sha(__file__),
        prior_code_sha256=sha(Path(__file__).with_name("analyse.py")),
        input_sha256=INPUTS,
        python=sys.version,
        executable=sys.executable,
        packages=env,
        git_revision=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        counts=dict(
            core_tests=54,
            core_success=int(result.status.eq("estimated").sum()),
            timing_scenarios=len(timing),
            timing_success=sum(x["status"] == "estimated" for x in timing),
            shared_component_coefficients=len(cd),
        ),
        output_sha256={
            p.name: sha(p)
            for p in OUT.iterdir()
            if p.is_file() and p.name != "run_manifest.json"
        },
    )
    (OUT / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print("DONE", manifest["counts"], flush=True)


if __name__ == "__main__":
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        start_run(OUT, CONFIG_PATH, roster=CFG["roster"])
        main()
        save(
            "numerical_warnings.csv",
            [
                dict(
                    category=x.category.__name__,
                    message=str(x.message),
                    file=x.filename,
                    line=x.lineno,
                )
                for x in captured
            ]
            or [dict(count=0)],
        )
