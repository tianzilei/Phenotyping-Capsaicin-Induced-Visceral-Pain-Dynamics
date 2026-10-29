"""Participant/block fixed effects and clustered covariance methods."""

import numpy as np
import pandas as pd
from scipy import stats


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
            max_leverage=float(max((np.einsum("ij,ji->", bread, h) for h in H))),
        )
    return result


def wild(prep, res, index=0, *, replicates, seed):
    X, Y, g, G, N, H, c, K = [prep[k] for k in ["X", "Y", "g", "G", "N", "H", "c", "K"]]
    keep = [k for k in range(K) if k != index]
    restricted = np.zeros(K)
    restricted[keep] = np.linalg.lstsq(X[:, keep], Y, rcond=None)[0]
    nullscore = c - np.einsum("gij,j->gi", H, restricted)
    bread = np.linalg.inv(H.sum(0))
    B = replicates
    rng = np.random.default_rng(seed)
    count = 0
    for start in range(0, B, 500):
        n = min(500, B - start)
        w = rng.choice([-1.0, 1.0], size=(n, G))
        delta = np.einsum("bg,gk,kj->bj", w, nullscore, bread, optimize=False)
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
    s1, s2, vectors = ([], [], [])
    for g in range(p["G"]):
        ix = np.flatnonzero(p["g"] == g)
        Xg = D[ix]
        s1.append(np.einsum("ni,n->i", Xg, u[ix]))
        Rg = np.eye(len(ix)) - H[np.ix_(ix, ix)]
        eig, V = np.linalg.eigh((Rg + Rg.T) / 2)
        if eig.min() < -1e-08:
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
        r["correction"] * sum((np.einsum("i,i->", bread[0], s) ** 2 for s in s1))
    )
    se2 = np.sqrt(sum((np.einsum("i,i->", bread[0], s) ** 2 for s in s2)))
    Vectors = np.asarray(vectors)
    gram = np.einsum("in,jn->ij", Vectors, Vectors)
    df2 = np.trace(gram) ** 2 / np.sum(gram**2)
    ci = stats.t.ppf(0.975, df2) * se2
    assert abs(beta[0] - r["b"][0]) < 1e-08
    assert abs(se1 - r["se"][0]) < 1e-08
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
