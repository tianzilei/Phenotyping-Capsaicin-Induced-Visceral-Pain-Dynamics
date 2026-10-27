from analyse import *
from scipy import linalg


def direct(d, y, predictors):
    d = d.sort_values(["person_id", "block"])
    ids = pd.Categorical(d.person_id).codes
    G = len(set(ids))
    N = len(d)
    # Explicit full participant intercepts, slope and block columns; no absorption.
    person = np.eye(G)[ids]
    block = pd.get_dummies(d.block, drop_first=True, dtype=float).to_numpy()
    X = np.column_stack([d[predictors].to_numpy(), block, person])
    Y = d[y].to_numpy()
    K = X.shape[1]
    b = linalg.lstsq(X, Y, lapack_driver="gelsy")[0]
    e = Y - np.einsum("ij,j->i", X, b)
    gram = np.einsum("ni,nj->ij", X, X)
    bread = linalg.inv(gram)
    score = np.array([np.einsum("ni,n->i", X[ids == g], e[ids == g]) for g in range(G)])
    projected = np.einsum("gi,ij->gj", score, bread)
    cov = (G / (G - 1) * (N - 1) / (N - K)) * np.einsum(
        "gi,gj->ij", projected, projected
    )
    return b[: len(predictors)], np.sqrt(np.diag(cov))[: len(predictors)]


if __name__ == "__main__":
    require_missing(
        OUT, ["independent_covariance_verification.csv", "verification.json"]
    )
    res = pd.read_csv(OUT / "all_161_results.csv")
    checks = []
    # Validate all 156 coefficients using explicitly included participant intercepts.
    for name, path, grouper, y, predictors, family in [
        (
            "VAS",
            S["associations"] / "model_input_private.csv",
            ["roi", "metric"],
            "value",
            ["vas_mean"],
            "VAS_features",
        ),
        (
            "EGG",
            COMP / "egg_hb_model_inputs_private.csv",
            ["roi", "metric", "predictor"],
            "hb_within_person_SD",
            ["egg_value"],
            "EGG_Hb",
        ),
        (
            "JOINT",
            COMP / "joint_model_inputs_private.csv",
            ["roi", "metric"],
            "vas_mean",
            ["candidate_HR", "candidate_RR_RMSSD", "hb_within_person_SD"],
            "joint_VAS",
        ),
    ]:
        data = pd.read_csv(path)
        for keys, d in data.groupby(grouper, sort=True):
            b, se = direct(d, y, predictors)
            roi, metric = keys[:2]
            target = res[
                (res.family == family) & (res.roi == roi) & (res.metric == metric)
            ]
            if len(keys) == 3:
                target = target[target.predictor == keys[2]]
            for j, predictor in enumerate(predictors):
                r = (
                    target.iloc[0]
                    if len(predictors) == 1
                    else target[target.predictor == predictor].iloc[0]
                )
                assert abs(b[j] - r.beta) < 1e-9 and abs(se[j] - r.se_CR1) < 1e-9
                checks.append(
                    dict(
                        family=family,
                        roi=roi,
                        metric=metric,
                        predictor=r.predictor,
                        beta_abs_difference=abs(b[j] - r.beta),
                        se_abs_difference=abs(se[j] - r.se_CR1),
                    )
                )
        print("full-design validation", name, flush=True)
    write("independent_covariance_verification.csv", checks)
    for method in ["by", "bh"]:
        expected = stats.false_discovery_control(res.p_CR1.to_numpy(), method=method)
        np.testing.assert_allclose(
            expected, res["q_" + method.upper() + "_global161"], atol=1e-13
        )
        for fam, d in res.groupby("family"):
            np.testing.assert_allclose(
                stats.false_discovery_control(d.p_CR1.to_numpy(), method=method),
                d["q_" + method.upper() + "_family"],
                atol=1e-13,
            )
    # Wild contractions compared with literal re-fitted rows and explicit cluster scores.
    data = pd.read_csv(S["associations"] / "model_input_private.csv")
    wildchecks = []
    for roi, metric in [("ECG", "HR"), ("Frontal_Mid_L", "HbR")]:
        p = prepare(
            data[(data.roi == roi) & (data.metric == metric)], "value", ["vas_mean"]
        )
        X, Y, g, H, c, G, K = [p[k] for k in ["X", "Y", "g", "H", "c", "G", "K"]]
        r = fit(p)
        bread = np.linalg.inv(H.sum(0))
        b0 = np.zeros(K)
        b0[1:] = linalg.lstsq(X[:, 1:], Y, lapack_driver="gelsy")[0]
        u0 = Y - np.einsum("ij,j->i", X, b0)
        s0 = c - np.einsum("gij,j->gi", H, b0)
        rng = np.random.default_rng(CFG["inference"]["wild_cluster"]["seed"])
        w = rng.choice([-1.0, 1.0], size=(40, G))
        delta = np.einsum("bg,gk,kj->bj", w, s0, bread, optimize=False)
        proj = np.einsum("gi,i->g", s0, bread[:, 0])[None, :] * w - np.einsum(
            "gj,bj->bg", np.einsum("gij,i->gj", H, bread[:, 0]), delta
        )
        se_vec = np.sqrt(r["correction"] * np.sum(proj**2, axis=1))
        t_vec = delta[:, 0] / se_vec
        for k in range(40):
            ys = np.einsum("ij,j->i", X, b0) + u0 * w[k, g]
            bs = linalg.lstsq(X, ys, lapack_driver="gelsy")[0]
            us = ys - np.einsum("ij,j->i", X, bs)
            scores = np.array(
                [np.einsum("ni,n->i", X[g == i], us[g == i]) for i in range(G)]
            )
            v = r["correction"] * np.sum(np.einsum("gi,i->g", scores, bread[:, 0]) ** 2)
            t = bs[0] / np.sqrt(v)
            assert abs(t - t_vec[k]) < 1e-10
            wildchecks.append(abs(t - t_vec[k]))
    # Edge contracts: duplicate participant/block and constant exposure fail explicitly.
    fixture = pd.DataFrame(
        {
            "person_id": ["a", "a", "b", "b"],
            "block": [1, 2, 1, 2],
            "y": [1.0, 2.0, 4.0, 3.0],
            "x": [1.0, 1.0, 1.0, 1.0],
        }
    )
    failures = []
    for d in [pd.concat([fixture, fixture.iloc[[0]]]), fixture]:
        try:
            prepare(d, "y", ["x"])
            failures.append(False)
        except ValueError:
            failures.append(True)
    assert all(failures)
    # Compare both independent executions; v1 retained due BLAS floating-point-status warnings.
    v1 = pd.read_csv(
        OUT.parent / "physiology_inference_20261017_v1/all_161_results.csv"
    )
    mx = {}
    for col in ["beta", "se_CR1", "p_CR1", "p_wild"]:
        arr = abs(res[col] - v1[col])
        mx[col] = float(arr.max())
        assert arr.dropna().max() < 1e-10
    state = {
        "status": "PASS",
        "explicit_design_coefficients_verified": len(checks),
        "max_beta_difference": max(r["beta_abs_difference"] for r in checks),
        "max_se_difference": max(r["se_abs_difference"] for r in checks),
        "wild_replicates_independently_verified": len(wildchecks),
        "max_wild_t_difference": max(wildchecks),
        "FDR_independent_scipy_check": "PASS",
        "duplicate_and_rank_edge_checks": "PASS",
        "v1_v2_max_differences": mx,
        "warnings_v2": sum(
            "Warning" in line
            for line in (OUT / "execution.log").read_text().splitlines()
        ),
    }
    assert state["warnings_v2"] == 0
    (OUT / "verification.json").write_text(json.dumps(state, indent=2))
    print(json.dumps(state), flush=True)
