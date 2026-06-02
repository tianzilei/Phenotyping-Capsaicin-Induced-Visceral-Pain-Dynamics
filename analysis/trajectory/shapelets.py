"""
Time-series shapelet extraction for cluster discrimination.
Finds discriminative subsequences that characterize each cluster.
"""

from typing import Tuple

import numpy as np
import pandas as pd
from tslearn.metrics import dtw


def z_norm(x: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """
    Z-normalize a time series.

    Parameters
    ----------
    x : np.ndarray
        Input time series.
    eps : float
        Small constant to avoid division by zero.

    Returns
    -------
    np.ndarray
        Z-normalized time series.
    """
    x = np.asarray(x, dtype=float)
    return (x - x.mean()) / (x.std() + eps)


def min_subseq_distance(series: np.ndarray, shapelet: np.ndarray) -> Tuple[float, int]:
    """
    Compute minimum DTW distance between a shapelet and all subsequences
    of the same length in a series.

    Parameters
    ----------
    series : np.ndarray
        Full time series.
    shapelet : np.ndarray
        Candidate shapelet subsequence.

    Returns
    -------
    tuple of (float, int)
        (minimum distance, position of best match).
    """
    L = len(shapelet)
    s = np.asarray(series, dtype=float)
    sh = np.asarray(shapelet, dtype=float)

    best = np.inf
    best_pos = None

    for start in range(len(s) - L + 1):
        window = s[start : start + L]
        d = dtw(window.reshape(-1, 1), sh.reshape(-1, 1))
        if d < best:
            best = d
            best_pos = start

    return best, best_pos


def effect_size_d(pos_vals: np.ndarray, neg_vals: np.ndarray) -> float:
    """
    Compute Cohen's d effect size between positive and negative classes.

    Parameters
    ----------
    pos_vals : np.ndarray
        Distances for positive class (target cluster).
    neg_vals : np.ndarray
        Distances for negative class (other clusters).

    Returns
    -------
    float
        Cohen's d value (positive means shapelet is discriminative).
    """
    eps = 1e-8
    pos_vals = np.asarray(pos_vals, dtype=float)
    neg_vals = np.asarray(neg_vals, dtype=float)

    m1, m0 = pos_vals.mean(), neg_vals.mean()
    s1, s0 = pos_vals.std(ddof=1), neg_vals.std(ddof=1)
    n1, n0 = len(pos_vals), len(neg_vals)

    pooled = np.sqrt(((n1 - 1) * s1**2 + (n0 - 1) * s0**2) / max(n1 + n0 - 2, 1) + eps)
    return (m0 - m1) / pooled


def shapelet_score(distances: np.ndarray, y_binary: np.ndarray) -> Tuple[float, float]:
    """
    Score a shapelet by one-vs-rest separation using AUC and Cohen's d.

    Parameters
    ----------
    distances : np.ndarray
        Distance from shapelet to each sample.
    y_binary : np.ndarray
        Binary labels (1 = target cluster, 0 = other).

    Returns
    -------
    tuple of (float, float)
        (AUC, Cohen's d).
    """
    from sklearn.metrics import roc_auc_score

    distances = np.asarray(distances, dtype=float)
    y_binary = np.asarray(y_binary, dtype=int)

    auc = roc_auc_score(y_binary, -distances)

    pos = distances[y_binary == 1]
    neg = distances[y_binary == 0]
    d = effect_size_d(pos, neg)

    return auc, d


def corr_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compute correlation-based similarity between two shapelets.

    Parameters
    ----------
    a, b : np.ndarray
        Shapelet subsequences.

    Returns
    -------
    float
        Correlation coefficient.
    """
    a = z_norm(a)
    b = z_norm(b)
    if len(a) != len(b):
        return 0.0
    return np.corrcoef(a, b)[0, 1]


def extract_shapelets(
    X: np.ndarray,
    labels: np.ndarray,
    n_clusters: int = 3,
    min_len: int = 3,
    max_len: int = 8,
    top_k: int = 5,
    redundancy_corr_threshold: float = 0.90,
) -> pd.DataFrame:
    """
    Extract discriminative shapelets for each cluster.

    Parameters
    ----------
    X : np.ndarray
        tslearn-format time series data.
    labels : np.ndarray
        Cluster labels.
    n_clusters : int
        Number of clusters.
    min_len : int
        Minimum shapelet length.
    max_len : int
        Maximum shapelet length.
    top_k : int
        Number of top shapelets to keep per cluster.
    redundancy_corr_threshold : float
        Correlation threshold for redundancy removal.

    Returns
    -------
    pd.DataFrame
        Shapelet results with columns: target_cluster, source_subject,
        start, length, auc, cohens_d, shapelet values.
    """
    X_2d = X.squeeze() if X.ndim == 3 else X
    n_samples, T = X_2d.shape

    # Build candidate subsequences
    candidates = []
    for i in range(n_samples):
        series = X_2d[i]
        for L in range(min_len, max_len + 1):
            for start in range(T - L + 1):
                subseq = series[start : start + L].copy()
                candidates.append(
                    {
                        "subject_idx": i,
                        "start": start,
                        "length": L,
                        "subseq": subseq,
                    }
                )

    # One-vs-rest search for each cluster
    all_shapelets = []

    for target_cluster in range(n_clusters):
        y = (labels == target_cluster).astype(int)

        results = []
        for c_idx, cand in enumerate(candidates):
            shapelet = cand["subseq"]
            dists = []
            for i in range(n_samples):
                d, _ = min_subseq_distance(X_2d[i], shapelet)
                dists.append(d)

            dists = np.array(dists)
            auc, d = shapelet_score(dists, y)

            results.append(
                {
                    "target_cluster": target_cluster + 1,
                    "candidate_idx": c_idx,
                    "source_subject": cand["subject_idx"],
                    "start": cand["start"],
                    "length": cand["length"],
                    "auc": auc,
                    "cohens_d": d,
                    "mean_dist_target": dists[y == 1].mean(),
                    "mean_dist_other": dists[y == 0].mean(),
                    "subseq": shapelet,
                }
            )

        # Sort by AUC then Cohen's d
        results.sort(key=lambda x: (x["auc"], x["cohens_d"]), reverse=True)

        # Remove redundant shapelets
        selected = []
        for r in results:
            keep = True
            for s in selected:
                if r["length"] == s["length"]:
                    sim = corr_similarity(r["subseq"], s["subseq"])
                    if abs(sim) >= redundancy_corr_threshold:
                        keep = False
                        break
            if keep:
                selected.append(r)
            if len(selected) >= top_k:
                break

        all_shapelets.extend(selected)

    # Convert to DataFrame
    rows = []
    for s in all_shapelets:
        row = {
            "target_cluster": s["target_cluster"],
            "source_subject": s["source_subject"],
            "start": s["start"],
            "length": s["length"],
            "auc": s["auc"],
            "cohens_d": s["cohens_d"],
            "mean_dist_target": s["mean_dist_target"],
            "mean_dist_other": s["mean_dist_other"],
        }
        for j, v in enumerate(s["subseq"], start=1):
            row[f"shapelet_pt{j}"] = v
        rows.append(row)

    return pd.DataFrame(rows)
