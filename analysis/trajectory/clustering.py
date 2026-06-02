"""
DTW-based clustering for VAS trajectories.
Includes DTW-KMeans, Fuzzy C-Medoids, and silhouette analysis.
"""

from typing import Tuple

import numpy as np
import pandas as pd
from tslearn.clustering import TimeSeriesKMeans
from tslearn.metrics import cdist_dtw
from tslearn.preprocessing import TimeSeriesScalerMeanVariance
from tslearn.utils import to_time_series_dataset


def prepare_vas_data(
    df: pd.DataFrame,
    time_cols: list,
    normalize: bool = True,
) -> Tuple[np.ndarray, np.ndarray, TimeSeriesKMeans]:
    """
    Load, clean, and format VAS data for tslearn.

    Parameters
    ----------
    df : pd.DataFrame
        Raw VAS DataFrame with time columns.
    time_cols : list of str
        Time column names (e.g., ['1min', '2min', ...]).
    normalize : bool
        Whether to apply z-normalization.

    Returns
    -------
    tuple of (np.ndarray, np.ndarray, TimeSeriesScalerMeanVariance or None)
        X (tslearn format), X_raw (n_samples, n_timepoints), scaler (or None).
    """

    # Clean data: E/T censoring (propagate NaN after first E/T), then interpolate gaps
    def censor_et(row):
        """Once E/T appears, set all subsequent values to NaN."""
        result = row.copy()
        for i, val in enumerate(row):
            if str(val) in ("E", "T"):
                result.iloc[i:] = np.nan
                break
        return result

    data = df[time_cols].apply(censor_et, axis=1)
    data = data.apply(pd.to_numeric, errors="coerce")

    # Interpolate only pre-censoring gaps, fill remaining with 0
    data = data.interpolate(axis=1, limit_area="inside").fillna(0)

    X_raw = data.values

    # Convert to tslearn format
    X = to_time_series_dataset(X_raw)

    # Normalize
    scaler = None
    if normalize:
        scaler = TimeSeriesScalerMeanVariance()
        X = scaler.fit_transform(X)

    return X, X_raw, scaler


def dtw_kmeans_cluster(
    X: np.ndarray,
    n_clusters: int = 3,
    max_iter: int = 50,
    random_state: int = 42,
    verbose: bool = False,
) -> Tuple[np.ndarray, np.ndarray, TimeSeriesKMeans]:
    """
    Perform DTW-KMeans clustering.

    Parameters
    ----------
    X : np.ndarray
        tslearn-format time series data.
    n_clusters : int
        Number of clusters.
    max_iter : int
        Maximum iterations.
    random_state : int
        Random seed.
    verbose : bool
        Whether to print iteration info.

    Returns
    -------
    tuple of (np.ndarray, np.ndarray, TimeSeriesKMeans)
        labels, centroids, fitted model.
    """
    model = TimeSeriesKMeans(
        n_clusters=n_clusters,
        metric="dtw",
        max_iter=max_iter,
        random_state=random_state,
        n_jobs=-1,
        verbose=verbose,
    )

    labels = model.fit_predict(X)
    centroids = model.cluster_centers_

    return labels, centroids, model


def compute_dtw_silhouette(
    X: np.ndarray, labels: np.ndarray
) -> Tuple[float, np.ndarray]:
    """
    Compute DTW-based silhouette score.

    Parameters
    ----------
    X : np.ndarray
        tslearn-format time series data.
    labels : np.ndarray
        Cluster labels.

    Returns
    -------
    tuple of (float, np.ndarray)
        Average silhouette score, per-sample silhouette values.
    """
    from sklearn.metrics import silhouette_samples, silhouette_score

    X_2d = X.squeeze() if X.ndim == 3 else X

    # Pairwise DTW distance matrix
    dtw_dist_matrix = cdist_dtw(X_2d)

    # Silhouette score
    sil_avg = silhouette_score(dtw_dist_matrix, labels, metric="precomputed")
    sil_values = silhouette_samples(dtw_dist_matrix, labels, metric="precomputed")

    return sil_avg, sil_values


def select_optimal_k(
    X: np.ndarray,
    k_range: range = range(2, 7),
    max_iter: int = 50,
    random_state: int = 42,
) -> pd.DataFrame:
    """
    Evaluate DTW-KMeans across different K values.

    Parameters
    ----------
    X : np.ndarray
        tslearn-format time series data.
    k_range : range
        Range of K values to test.
    max_iter : int
        Maximum iterations per K.
    random_state : int
        Random seed.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: K, DTW_silhouette.
    """
    results = []

    for k in k_range:
        labels_k, _, _ = dtw_kmeans_cluster(
            X, n_clusters=k, max_iter=max_iter, random_state=random_state
        )
        sil_avg, _ = compute_dtw_silhouette(X, labels_k)
        results.append({"K": k, "DTW_silhouette": sil_avg})

    return pd.DataFrame(results)


def fuzzy_c_medoids(
    X: np.ndarray,
    n_clusters: int = 3,
    m: float = 2.0,
    max_iter: int = 200,
    tol: float = 1e-5,
    random_state: int = 42,
    return_history: bool = False,
) -> Tuple:
    """
    Perform DTW-based Fuzzy C-Medoids clustering.

    Parameters
    ----------
    X : np.ndarray
        tslearn-format time series data.
    n_clusters : int
        Number of clusters.
    m : float
        Fuzziness parameter (typically 1.5-2.5).
    max_iter : int
        Maximum iterations.
    tol : float
        Convergence tolerance.
    random_state : int
        Random seed.
    return_history : bool
        If True, also return the objective function history per iteration.

    Returns
    -------
    tuple
        labels (hard), memberships (U), medoid_indices, [optional] objective_history.
    """
    X_2d = X.squeeze() if X.ndim == 3 else X
    n_samples = X_2d.shape[0]

    # Pairwise DTW distance matrix
    D = cdist_dtw(X_2d)

    EPS = 1e-12

    # Initialize medoids randomly
    rng = np.random.default_rng(random_state)
    medoid_indices = rng.choice(n_samples, size=n_clusters, replace=False)

    def _update_memberships(D_to_medoids, m=2.0, eps=1e-12):
        n, c = D_to_medoids.shape
        U = np.zeros((n, c), dtype=float)
        power = 2.0 / (m - 1.0)

        for i in range(n):
            d_i = D_to_medoids[i].copy()
            zero_idx = np.where(d_i <= eps)[0]
            if len(zero_idx) > 0:
                U[i, zero_idx[0]] = 1.0
                continue
            for k in range(c):
                denom = np.sum((d_i[k] / (d_i + eps)) ** power)
                U[i, k] = 1.0 / (denom + eps)

        U = U / U.sum(axis=1, keepdims=True)
        return U

    def _objective(U, D_to_medoids, m=2.0):
        return np.sum((U**m) * (D_to_medoids**2))

    def _update_medoids(D, U, m=2.0):
        n, c = U.shape
        new_medoids = np.zeros(c, dtype=int)
        for k in range(c):
            weights = U[:, k] ** m
            costs = np.sum(weights[:, None] * (D**2), axis=0)
            new_medoids[k] = np.argmin(costs)
        return new_medoids

    history = []

    # Iterate
    for it in range(max_iter):
        D_to_medoids = D[:, medoid_indices]
        U = _update_memberships(D_to_medoids, m=m, eps=EPS)

        if return_history:
            history.append(_objective(U, D_to_medoids, m=m))

        new_medoids = _update_medoids(D, U, m=m)

        if np.array_equal(new_medoids, medoid_indices):
            medoid_indices = new_medoids
            break

        medoid_indices = new_medoids

    # Final memberships
    D_to_medoids = D[:, medoid_indices]
    U = _update_memberships(D_to_medoids, m=m, eps=EPS)
    labels = np.argmax(U, axis=1)

    if return_history:
        return labels, U, medoid_indices, history
    return labels, U, medoid_indices
