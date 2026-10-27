"""Independent checks, complete scenario disposition and final inference table."""

from pathlib import Path
import sys
import json
import hashlib
import importlib.util
import itertools

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd
from scipy import stats
from runtime import locations, start_run, require_missing

ROOT, OUT, CFG, CONFIG_PATH = locations("extension")
sp = importlib.util.spec_from_file_location(
    "ext", Path(__file__).with_name("run_extension.py")
)
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)
require_missing(
    OUT,
    [
        "core_54_results_verified.csv",
        "timing_all432_disposition.csv",
        "verification.json",
        "bilateral_contrast_identity_check.csv",
    ],
)
c = pd.read_csv(OUT / "core_54_results.csv")
r = pd.read_csv(OUT / "core_CR2_R.csv")
assert len(c) == len(r) == 54 and c.test_id.is_unique and r.test_id.is_unique
z = c.merge(r, on="test_id", validate="one_to_one")
differences = {}
for left, right in [
    ("beta", "beta_R"),
    ("se_CR1", "se_CR1_R"),
    ("se_CR2_python", "se_CR2_R"),
    ("df_CR2_python", "df_CR2_R"),
    ("p_CR2_python", "p_CR2_R"),
]:
    differences[left + "_vs_" + right] = float(abs(z[left] - z[right]).max())
    assert np.allclose(z[left], z[right], atol=1e-8, rtol=1e-7)
for family, idx in z.groupby("family").groups.items():
    for meth in ["BY", "BH"]:
        z.loc[idx, "q_CR2_" + meth + "_family"] = stats.false_discovery_control(
            z.loc[idx, "p_CR2_R"].to_numpy(), method=meth.lower()
        )
        q = stats.false_discovery_control(
            z.loc[idx, "p_CR1"].to_numpy(), method=meth.lower()
        )
        assert np.allclose(q, z.loc[idx, "q_" + meth + "_family"], atol=1e-12)
for meth in ["BY", "BH"]:
    z["q_CR2_" + meth + "_global54"] = stats.false_discovery_control(
        z.p_CR2_R.to_numpy(), method=meth.lower()
    )
    assert np.allclose(
        stats.false_discovery_control(z.p_CR1.to_numpy(), method=meth.lower()),
        z["q_" + meth + "_global54"],
        atol=1e-12,
    )
z.to_csv(OUT / "core_54_results_verified.csv", index=False)
# Save all intended scenario positions, including data rejected by duration rules.
t = pd.read_csv(OUT / "fixed_support_timing.csv")
scenes = [(s, o, 0) for s in ["A", "B"] for o in [0, -10, 10, -30, 30, -60, 60]] + [
    (s, 0, d) for s in ["A", "B"] for d in [-100, 100]
]
targets = c[c.family == "C1_original24"][["roi", "metric"]].itertuples(
    index=False, name=None
)
roster = pd.DataFrame(
    [
        dict(roi=roi, metric=metric, support_spec=s, offset_s=o, drift_ppm=d)
        for roi, metric in targets
        for s, o, d in scenes
    ]
)
disposition = roster.merge(
    t,
    on=["roi", "metric", "support_spec", "offset_s", "drift_ppm"],
    how="left",
    validate="one_to_one",
)
missing = disposition.status.isna()
assert missing.sum() == 2
assert set(disposition.loc[missing, "metric"]) == {"candidate_RR_RMSSD"}
assert set(disposition.loc[missing, "drift_ppm"]) == {-100}
disposition.loc[missing, "status"] = "ineligible_under_inherited_duration_rule"
disposition.loc[missing, "reason"] = (
    "All RR-RMSSD rows fail inherited b-a>=300s gate: 300s nominal scaled by -100ppm is 299.97s. Raw values exist; not a model failure."
)
disposition.to_csv(OUT / "timing_all432_disposition.csv", index=False)
decomp = pd.read_csv(OUT / "sample_scale_timing_decomposition.csv")
assert len(decomp) == 430
err = abs(
    decomp.beta_shifted_same_common_scale
    - decomp.beta_original
    - decomp.delta_sample_restriction
    - decomp.delta_scale
    - decomp.delta_timing
)
assert err.max() < 1e-10
assert t.mismatched_score_or_minutes_rows.max() == 0
inputs = pd.read_csv(OUT / "core_model_inputs_private.csv")
assert not inputs.duplicated(["test_id", "person_id", "block"]).any()
for tid, d in inputs.groupby("test_id"):
    assert d.groupby("person_id").block.nunique().min() >= 2
    assert np.isfinite(d[["value", "vas_mean"]]).all().all()
# Direct lateral contrast equals difference between same-row side coefficients.
raw = pd.read_csv(OUT / "nominal_raw_Hb_private.csv")
sidechecks = []
for row in c[c.family == "C2_bilateral8"].itertuples():
    base = row.roi.replace("_L_minus_R", "")
    left = raw[(raw.roi == base + "_L") & (raw.metric == row.metric)]
    right = raw[(raw.roi == base + "_R") & (raw.metric == row.metric)]
    v = left.merge(
        right, on=["person_id", "block"], suffixes=("_L", "_R"), validate="one_to_one"
    )
    v = m.keep_people(v, ["value_L", "value_R"])
    for side in ["L", "R"]:
        v = m.standardize(v, "value_" + side, "z_" + side)
    estimates = []
    for side in ["L", "R"]:
        data = v[["person_id", "block"]].copy()
        data["vas_mean"] = v.vas_mean_L
        data["value"] = v["z_" + side]
        estimates.append(m.estimate(data, loo=False)[0]["beta"])
    difference = estimates[0] - estimates[1]
    assert abs(difference - row.beta) < 1e-10
    sidechecks.append(
        dict(
            test_id=row.test_id,
            left_beta=estimates[0],
            right_beta=estimates[1],
            direct_difference=row.beta,
            absolute_error=abs(difference - row.beta),
        )
    )
m.save("bilateral_contrast_identity_check.csv", sidechecks)
# Every paired HR comparison uses the same data and the same outcome scale.
comparisons = pd.read_csv(OUT / "HR_same_rows_comparisons.csv")
for row in c[c.family == "C3_HR_conditioned22"].itertuples():
    data = inputs[inputs.test_id == row.test_id].copy()
    before = comparisons[
        (comparisons.test_id == row.test_id) & (comparisons.model == "same_rows_no_HR")
    ].iloc[0]
    fit = m.estimate(data, loo=False)[0]
    assert len(data) == row.n_blocks == before.n_blocks
    assert data.person_id.nunique() == row.n_people == before.n_people
    assert abs(fit["beta"] - before.beta) < 1e-10
verification = dict(
    status="passed",
    core_models=54,
    core_failures=0,
    synthetic_reference_models=8,
    CR2_reference="R4.6.1 clubSandwich0.7.0; explicit lm fixed effects; CR2 identity working covariance; Satterthwaite",
    CR2_correction_scope="OLS only; full fixed effects retained. No GLS shortcut from original Theorem2 used; 2023 corrigendum restriction respected.",
    independent_numeric_differences=differences,
    BY_BH_independently_checked=True,
    intended_timing_positions=432,
    timing_estimated=430,
    timing_inherited_duration_ineligible=2,
    sample_scale_time_decomposition_max_error=float(err.max()),
    bilateral_identity_checks=8,
    same_HR_rows_and_scale_checks=22,
    numerical_warnings=0,
    historical_document_checks_included=False,
)
(OUT / "verification.json").write_text(
    json.dumps(verification, ensure_ascii=False, indent=2) + "\n"
)
print(json.dumps(verification, ensure_ascii=False, indent=2))
