"""Unmodified numerical kernels extracted from run_reanalysis_clustering.py."""

import numpy as np
from scipy.spatial.distance import cdist
from sklearn.cluster import KMeans


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
