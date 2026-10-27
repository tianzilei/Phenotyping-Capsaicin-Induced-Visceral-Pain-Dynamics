"""Exploratory physiological inference. Frozen configuration is authoritative."""

from pathlib import Path
import sys
import json
import hashlib
import subprocess
import platform
import datetime
import importlib.metadata
import numpy as np
import pandas as pd
from scipy import stats
from runtime import locations, start_run, require_missing

ROOT, OUT, CFG, CONFIG_PATH = locations("inference")
S = {k: ROOT / v for k, v in CFG["sources"].items() if not Path(v).is_absolute()}
COMP = ROOT / "08_outputs/analysis_completion_20261002T152859Z_12f7386c"
INPUTS = {}
CHECKS = []


def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def loadcsv(p, verify=True, **kwargs):
    p = Path(p)
    digest = sha(p)
    INPUTS[str(p)] = digest
    if verify:
        found = []
        for name in ["manifest.json", "run_manifest.json"]:
            m = p.parent / name
            if m.exists():
                INPUTS[str(m)] = sha(m)
                d = json.loads(m.read_text(encoding="utf-8-sig"))
                for field in ["outputs_sha256", "output_sha256"]:
                    for key, val in d.get(field, {}).items():
                        if key.replace("\\", "/").split("/")[
                            -1
                        ] == p.name and isinstance(val, str):
                            found.append(val)
        if not found:
            raise ValueError("no inherited hash " + str(p))
        if any(v != digest for v in found):
            raise ValueError("inherited hash mismatch " + str(p))
        CHECKS.append({"file": str(p), "sha256": digest, "inherited_hash_match": True})
    return pd.read_csv(p, encoding="utf-8-sig", **kwargs)


def write(name, rows):
    pd.DataFrame(rows).to_csv(OUT / name, index=False, mode="x")


def prepare(d, y, x, person="person_id", block="block", demean=True):
    d = d.copy().sort_values([person, block]).reset_index(drop=True)
    if d.duplicated([person, block]).any():
        raise ValueError("duplicate analysis unit")
    cols = [y] + x
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors="raise")
    if not np.isfinite(d[cols]).all().all():
        raise ValueError("nonfinite model data")
    counts = d.groupby(person)[block].nunique()
    d = d[d[person].isin(counts[counts >= 2].index)].copy() if demean else d
    if not len(d):
        raise ValueError("no rows")
    g, ppl = pd.factorize(d[person], sort=True)
    G = len(ppl)
    N = len(d)
    z = pd.get_dummies(d[block].astype(int), drop_first=demean, dtype=float).to_numpy()
    a = np.column_stack([d[y].to_numpy(), d[x].to_numpy(), z])
    if demean:
        a -= pd.DataFrame(a).groupby(g).transform("mean").to_numpy()
    Y = a[:, 0]
    X = a[:, 1:]
    K = X.shape[1]
    if np.linalg.matrix_rank(X) != K:
        raise ValueError("rank deficient")
    H = np.zeros((G, K, K))
    c = np.zeros((G, K))
    for i in range(G):
        Xi = X[g == i]
        H[i] = np.einsum("ni,nj->ij", Xi, Xi)
        c[i] = np.einsum("ni,n->i", Xi, Y[g == i])
    return dict(
        d=d, g=g, G=G, N=N, X=X, Y=Y, H=H, c=c, K=K, absorbed=G if demean else 0
    )


def fit(prep, include_loo=True):
    p = prep
    X, Y, g, G, N, H, c, K = [p[k] for k in ["X", "Y", "g", "G", "N", "H", "c", "K"]]
    bread = np.linalg.inv(H.sum(0))
    b = np.einsum("ij,j->i", bread, c.sum(0))
    u = Y - np.einsum("ij,j->i", X, b)
    score = c - np.einsum("gij,j->gi", H, b)
    correction = G / (G - 1) * (N - 1) / (N - p["absorbed"] - K)
    cov = correction * np.einsum(
        "ij,gi,gk,kl->jl", bread, score, score, bread, optimize=False
    )
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    crit = stats.t.ppf(0.975, G - 1)
    pv = 2 * stats.t.sf(abs(b / se), G - 1)
    result = dict(
        b=b,
        se=se,
        low=b - crit * se,
        high=b + crit * se,
        p=pv,
        df=G - 1,
        cov=cov,
        sse=float(np.einsum("i,i->", u, u)),
        correction=correction,
    )
    if include_loo:
        leave = np.array(
            [np.linalg.solve(H.sum(0) - hi, c.sum(0) - ci) for hi, ci in zip(H, c)]
        )
        var = (G - 1) / G * np.sum((leave - leave.mean(0)) ** 2, axis=0)
        s3 = np.sqrt(var)
        result.update(
            se3=s3,
            low3=b - crit * s3,
            high3=b + crit * s3,
            p3=2 * stats.t.sf(abs(b / s3), G - 1),
            loo_min=leave.min(0),
            loo_max=leave.max(0),
            loo_sign_changes=np.sum(np.sign(leave) != np.sign(b), axis=0),
            max_leverage=float(max(np.einsum("ij,ji->", bread, h) for h in H)),
        )
    return result


def wild(prep, res, index=0):
    X, Y, g, G, N, H, c, K = [prep[k] for k in ["X", "Y", "g", "G", "N", "H", "c", "K"]]
    keep = [k for k in range(K) if k != index]
    restricted = np.zeros(K)
    restricted[keep] = np.linalg.lstsq(X[:, keep], Y, rcond=None)[0]
    nullscore = c - np.einsum("gij,j->gi", H, restricted)
    bread = np.linalg.inv(H.sum(0))
    B = CFG["inference"]["wild_cluster"]["replicates"]
    rng = np.random.default_rng(CFG["inference"]["wild_cluster"]["seed"])
    count = 0
    for start in range(0, B, 500):
        n = min(500, B - start)
        w = rng.choice([-1.0, 1.0], size=(n, G))
        delta = np.einsum("bg,gk,kj->bj", w, nullscore, bread, optimize=False)
        # Each bootstrap cluster score is w_i X_i'r_i - H_i delta.
        projected = np.einsum("gi,i->g", nullscore, bread[:, index])[
            None, :
        ] * w - np.einsum(
            "gj,bj->bg", np.einsum("gij,i->gj", H, bread[:, index]), delta
        )
        se = np.sqrt(res["correction"] * np.sum(projected**2, axis=1))
        tv = delta[:, index] / se
        if not np.isfinite(tv).all():
            raise ValueError("nonfinite wild studentization")
        count += int(np.sum(abs(tv) >= abs(res["b"][index] / res["se"][index])))
    return dict(wild_exceedances=count, wild_replicates=B, p_wild=(count + 1) / (B + 1))


def row_of(p, r, j=0):
    return dict(
        n_people=p["G"],
        n_blocks=p["N"],
        beta=r["b"][j],
        se_CR1=r["se"][j],
        ci95_low=r["low"][j],
        ci95_high=r["high"][j],
        p_CR1=r["p"][j],
        df=r["df"],
        se_CR3=r["se3"][j],
        ci95_CR3_low=r["low3"][j],
        ci95_CR3_high=r["high3"][j],
        p_CR3=r["p3"][j],
        loo_beta_min=r["loo_min"][j],
        loo_beta_max=r["loo_max"][j],
        loo_sign_changes=int(r["loo_sign_changes"][j]),
        max_cluster_leverage=r["max_leverage"],
        residual_sse=r["sse"],
    )


def adjust(p, method="BY", n=None):
    p = np.asarray(p, float)
    q = np.full(len(p), np.nan)
    ix = np.flatnonzero(np.isfinite(p))
    m = len(p) if n is None else n
    order = ix[np.argsort(p[ix])]
    factor = sum(1 / np.arange(1, m + 1)) if method == "BY" else 1
    q[order] = np.minimum(
        1,
        np.minimum.accumulate(
            (p[order] * m * factor / np.arange(1, len(order) + 1))[::-1]
        )[::-1],
    )
    return q


if __name__ == "__main__":
    start_run(OUT, CONFIG_PATH)
    print("Starting explicit-source verification", flush=True)
    nominal = loadcsv(S["associations"] / "model_input_private.csv")
    old = loadcsv(S["associations"] / "planned_24_disposition.csv")
    egg = loadcsv(COMP / "egg_hb_model_inputs_private.csv")
    joint = loadcsv(COMP / "joint_model_inputs_private.csv")
    eggvas = loadcsv(COMP / "egg_block_candidates_private.csv")
    people = loadcsv(COMP / "people_private.csv")
    original_people = loadcsv(
        S["person_run"] / "BaselineData_person_private.csv", verify=False
    )
    pd.testing.assert_frame_equal(people, original_people)
    assert len(people) == 215 and people.ID.is_unique
    assert set(nominal.person_id) <= set(people.ID)
    assert set(egg.person_id) | set(joint.person_id) | set(eggvas.person_id) <= set(
        people.ID
    )
    print("Verified cohort and analysis tables", flush=True)
    results = []
    sens = []
    pointchecks = []
    for (roi, metric), d in nominal.groupby(["roi", "metric"], sort=True):
        p = prepare(d, "value", ["vas_mean"])
        r = fit(p)
        record = dict(
            family="VAS_features",
            roi=roi,
            metric=metric,
            predictor="vas_mean",
            unit="bpm/score"
            if metric == "HR"
            else "ms/score"
            if roi == "ECG"
            else "within_person_SD/score",
            **row_of(p, r),
            **wild(p, r),
        )
        results.append(record)
        ref = old[(old.roi == roi) & (old.metric == metric)].iloc[0]
        assert np.isclose(r["b"][0], ref.candidate_beta, atol=1e-10)
        pointchecks.append(
            dict(
                family="VAS_features",
                roi=roi,
                metric=metric,
                absolute_difference=abs(r["b"][0] - ref.candidate_beta),
            )
        )
        complete = d[
            d.person_id.isin(
                d.groupby("person_id").block.nunique().loc[lambda a: a == 4].index
            )
        ]
        if len(complete):
            pp = prepare(complete, "value", ["vas_mean"])
            rr = fit(pp)
            sens.append(
                dict(spec="all_four_blocks", roi=roi, metric=metric, **row_of(pp, rr))
            )
        dd = d.sort_values(["person_id", "block"]).copy()
        lag = dd.groupby("person_id")[["value", "vas_mean", "block"]].shift()
        valid = (dd.block - lag.block).eq(1)
        delta = dd.loc[valid, ["person_id", "block"]].copy()
        delta["dy"] = (dd.value - lag.value)[valid]
        delta["dx"] = (dd.vas_mean - lag.vas_mean)[valid]
        pp = prepare(delta, "dy", ["dx"], demean=False)
        rr = fit(pp)
        sens.append(
            dict(
                spec="strictly_adjacent_first_difference",
                roi=roi,
                metric=metric,
                **row_of(pp, rr),
            )
        )
        print("VAS-feature", roi, metric, flush=True)
    for (roi, metric, predictor), d in egg.groupby(
        ["roi", "metric", "predictor"], sort=True
    ):
        p = prepare(d, "hb_within_person_SD", ["egg_value"])
        r = fit(p)
        results.append(
            dict(
                family="EGG_Hb",
                roi=roi,
                metric=metric,
                predictor=predictor,
                unit="within_person_SD/EGG_descriptor",
                **row_of(p, r),
            )
        )
    for (roi, metric), d in joint.groupby(["roi", "metric"], sort=True):
        predictors = ["candidate_HR", "candidate_RR_RMSSD", "hb_within_person_SD"]
        p = prepare(d, "vas_mean", predictors)
        r = fit(p)
        for j, predictor in enumerate(predictors):
            results.append(
                dict(
                    family="joint_VAS",
                    roi=roi,
                    metric=metric,
                    predictor=predictor,
                    unit="score/physiological_unit",
                    **row_of(p, r, j),
                )
            )
    for predictor in ["peak_cpm", "log_power_1_9", "spectral_fraction_2_4"]:
        p = prepare(eggvas, predictor, ["vas_mean"])
        r = fit(p)
        results.append(
            dict(
                family="EGG_VAS",
                roi="EGG",
                metric=predictor,
                predictor="vas_mean",
                unit="EGG_descriptor/score",
                **row_of(p, r),
            )
        )
    # Rest source identity: match raw input SHA, then use a unique approved E per person.
    rest = loadcsv(S["e07"] / "rest_post_hrv_symmetric.csv")
    audit = loadcsv(S["ecg_egg"] / "record_audit_private.csv")
    aliases = json.loads((S["person_run"] / "aliases_private.json").read_text())
    INPUTS[str(S["person_run"] / "aliases_private.json")] = sha(
        S["person_run"] / "aliases_private.json"
    )
    manifest = json.loads((S["e07"] / "run_manifest.json").read_text())
    rawhash = {k.replace("\\", "/"): v for k, v in manifest["input_sha256"].items()}

    def key(path):
        text = str(path).replace("\\", "/")
        for prefix in [str(ROOT), "D:/capsaicin_analysis_2026-09-13"]:
            if text.casefold().startswith(prefix.casefold() + "/"):
                return text[len(prefix) + 1 :]
        raise ValueError("unregistered pair raw path")

    rest["person_id"] = rest.subject_id.map(lambda x: aliases.get(x, x))
    selected = set(zip(audit.person_id, audit.sha256))
    rest["selected_E_source"] = rest.apply(
        lambda r: (r.person_id, rawhash[key(r.post_path)]) in selected, axis=1
    )
    rest["in_current_cohort"] = rest.person_id.isin(people.ID)
    admitted = rest[rest.selected_E_source & rest.in_current_cohort].copy()
    ambiguous = set(admitted.loc[admitted.person_id.duplicated(False), "person_id"])
    rest["ambiguous_selected_pair"] = rest.person_id.isin(ambiguous)
    rest["included_new_analysis"] = (
        rest.selected_E_source
        & rest.in_current_cohort
        & ~rest.ambiguous_selected_pair
        & rest.paired_status.eq("E07_TIER_C_ESTIMATED")
    )
    write(
        "rest_pair_disposition_private.csv",
        rest[
            [
                "person_id",
                "selected_E_source",
                "in_current_cohort",
                "ambiguous_selected_pair",
                "paired_status",
                "included_new_analysis",
            ]
        ],
    )
    rest = rest[rest.included_new_analysis].copy()
    assert rest.person_id.is_unique
    rest_summary = {}
    for metric in ["candidate_hr_bpm", "candidate_rmssd_ms"]:
        pre = rest["base_" + metric].to_numpy()
        post = rest["post_" + metric].to_numpy()
        delta = post - pre
        n = len(delta)
        mean = delta.mean()
        se = stats.sem(delta)
        crit = stats.t.ppf(0.975, n - 1)
        pv = stats.ttest_1samp(delta, 0).pvalue
        rest_summary[metric] = dict(
            n=n,
            baseline_mean=pre.mean(),
            challenge_mean=post.mean(),
            baseline_median=np.median(pre),
            challenge_median=np.median(post),
            median_paired_change=np.median(delta),
            wilcoxon_sensitivity_p=stats.wilcoxon(delta).pvalue,
            positive=int(np.sum(delta > 0)),
            negative=int(np.sum(delta < 0)),
        )
        results.append(
            dict(
                family="rest_challenge",
                roi="ECG",
                metric=metric,
                predictor="challenge_minus_rest",
                unit="bpm" if metric == "candidate_hr_bpm" else "ms",
                n_people=n,
                n_blocks=2 * n,
                beta=mean,
                se_CR1=se,
                ci95_low=mean - crit * se,
                ci95_high=mean + crit * se,
                p_CR1=pv,
                df=n - 1,
            )
        )
    result = pd.DataFrame(results)
    assert len(result) == 161
    for family, idx in result.groupby("family").groups.items():
        assert len(idx) == CFG["families"][family]
        for meth in ["BY", "BH"]:
            result.loc[idx, "q_" + meth + "_family"] = adjust(
                result.loc[idx, "p_CR1"], meth
            )
            if family == "VAS_features":
                result.loc[idx, "q_wild_" + meth + "_24"] = adjust(
                    result.loc[idx, "p_wild"], meth
                )
    for meth in ["BY", "BH"]:
        result["q_" + meth + "_global161"] = adjust(result.p_CR1, meth)
        mask = result.family.eq("VAS_features")
        result.loc[mask, "q_wild_" + meth + "_global161"] = adjust(
            result.loc[mask, "p_wild"], meth, n=161
        )
        result["q_CR3_" + meth + "_global161"] = adjust(result.p_CR3, meth, n=161)
    write("all_161_results.csv", result)
    write("VAS_feature_sensitivities.csv", sens)
    write("point_estimate_verification.csv", pointchecks)
    (OUT / "rest_pair_summary.json").write_text(
        json.dumps(rest_summary, indent=2, default=lambda v: v.item())
    )
    write("source_hash_verification.csv", CHECKS)
    env = {
        k: importlib.metadata.version(k)
        for k in ["numpy", "pandas", "scipy", "bioread", "neurokit2"]
    }
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    (OUT / "run_manifest.json").write_text(
        json.dumps(
            dict(
                status="completed_core_inference",
                created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                configuration_sha256=sha(OUT / "frozen_config.json"),
                code_sha256=sha(__file__),
                input_sha256=INPUTS,
                python=sys.version,
                executable=sys.executable,
                packages=env,
                git_revision=revision,
                git_worktree="pre-existing modifications; new code snapshot is this file",
                output_sha256={
                    p.name: sha(p)
                    for p in OUT.iterdir()
                    if p.is_file() and p.name != "run_manifest.json"
                },
            ),
            indent=2,
        )
    )
    print(
        result.groupby("family")
        .apply(
            lambda d: pd.Series(
                {
                    "tests": len(d),
                    "BY_family_lt_05": sum(d.q_BY_family < 0.05),
                    "BY_global_lt_05": sum(d.q_BY_global161 < 0.05),
                }
            ),
            include_groups=False,
        )
        .to_string(),
        flush=True,
    )
    print("DONE", OUT, flush=True)
