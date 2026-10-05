"""Complete-case shape sensitivity, without imposing a clinical phenotype count."""

import json
import sys
import uuid
from pathlib import Path
import numpy as np
from scipy.spatial.distance import cdist
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from prepare_reanalysis_20260926 import ROOT, read, write, dump, sha

sys.path.insert(0, str(ROOT / "src"))
from capsaicin.reanalysis import numeric


def dtw(a, b, radius=2):
    n = len(a)
    prev = np.full(n + 1, np.inf)
    prev[0] = 0
    for i in range(1, n + 1):
        cur = np.full(n + 1, np.inf)
        for j in range(max(1, i - radius), min(n, i + radius) + 1):
            cur[j] = (a[i - 1] - b[j - 1]) ** 2 + min(prev[j], cur[j - 1], prev[j - 1])
        prev = cur
    return np.sqrt(prev[n])


def pam(d, k, seed):
    rng = np.random.default_rng(seed)
    med = [int(rng.integers(len(d)))]
    while len(med) < k:
        dist = np.min(d[:, med], axis=1)
        dist[med] = -1
        med.append(int(np.argmax(dist)))
    for _ in range(50):
        labels = np.argmin(d[:, med], axis=1)
        new = []
        for c in range(k):
            members = np.flatnonzero(labels == c)
            new.append(
                int(members[np.argmin(d[np.ix_(members, members)].sum(axis=1))])
                if len(members)
                else med[c]
            )
        if new == med:
            break
        med = new
    return med, np.argmin(d[:, med], axis=1)


def fuzzy(x, k, seed):
    centers = KMeans(k, n_init=5, random_state=seed).fit(x).cluster_centers_
    for _ in range(150):
        dist = np.maximum(cdist(x, centers), 1e-12)
        u = dist**-2
        u /= u.sum(axis=1, keepdims=True)
        weights = u**2
        new = weights.T @ x / weights.sum(axis=0)[:, None]
        if np.max(abs(new - centers)) < 1e-6:
            break
        centers = new
    return centers, u.argmax(axis=1), u


def main():
    run = Path(sys.argv[1]).resolve()
    out = run / ("clustering_" + uuid.uuid4().hex[:8])
    out.mkdir()
    cfg = json.loads((run / "frozen_config.json").read_text(encoding="utf-8"))
    rows = read(run / "BaselineData_person_private.csv")
    seed = cfg["seed"]
    rng = np.random.default_rng(seed)
    summaries = []
    stability = []
    assignments = []
    for end in [10, 20]:
        complete = [
            r
            for r in rows
            if all(numeric(r[f"VAS_{i}min"]) is not None for i in range(1, end + 1))
        ]
        x = np.array(
            [[float(r[f"VAS_{i}min"]) for i in range(1, end + 1)] for r in complete]
        )
        ids = [r["ID"] for r in complete]
        n = len(x)
        dd = np.zeros((n, n))
        for i in range(n):
            for j in range(i):
                dd[i, j] = dd[j, i] = dtw(x[i], x[j])
        for k in cfg["clustering"]["k"]:
            for method in cfg["clustering"]["methods"]:
                if method == "euclidean_kmeans":
                    fit = KMeans(k, n_init=20, random_state=seed).fit(x)
                    labels = fit.labels_
                elif method == "dtw_pam":
                    med, labels = pam(dd, k, seed)
                else:
                    centers, labels, u = fuzzy(x, k, seed)
                sizes = np.bincount(labels, minlength=k)
                sil = (
                    silhouette_score(dd, labels, metric="precomputed")
                    if method == "dtw_pam"
                    else silhouette_score(x, labels)
                )
                summaries.append(
                    dict(
                        end_min=end,
                        method=method,
                        k=k,
                        n=n,
                        silhouette=float(sil),
                        minimum_cluster_size=int(sizes.min()),
                        cluster_sizes=";".join(map(str, sizes)),
                        phenotype_status="exploratory_not_clinical",
                    )
                )
                assignments.extend(
                    dict(
                        person_id=sid,
                        end_min=end,
                        method=method,
                        k=k,
                        cluster=int(label),
                    )
                    for sid, label in zip(ids, labels)
                )
                for b in range(cfg["clustering"]["stability_bootstrap"]):
                    take = rng.integers(n, size=n)
                    s = seed + b
                    if method == "euclidean_kmeans":
                        pred = (
                            KMeans(k, n_init=5, random_state=s).fit(x[take]).predict(x)
                        )
                    elif method == "dtw_pam":
                        bm, _ = pam(dd[np.ix_(take, take)], k, s)
                        pred = dd[:, take[bm]].argmin(axis=1)
                    else:
                        bc, _, _ = fuzzy(x[take], k, s)
                        pred = cdist(x, bc).argmin(axis=1)
                    stability.append(
                        dict(
                            end_min=end,
                            method=method,
                            k=k,
                            replicate=b,
                            ari=float(adjusted_rand_score(labels, pred)),
                        )
                    )
                write(out / "cluster_summary.csv", summaries)
                write(out / "stability.csv", stability)
                write(out / "assignments_private.csv", assignments)
                print("cluster", end, k, method, flush=True)
    dump(
        out / "manifest.json",
        dict(
            status="completed_exploratory",
            config_sha256=sha(run / "frozen_config.json"),
            code_sha256=sha(__file__),
            input_sha256=sha(run / "BaselineData_person_private.csv"),
            outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
        ),
    )
    (out / "execution_script.py").write_bytes(Path(__file__).read_bytes())


if __name__ == "__main__":
    main()
