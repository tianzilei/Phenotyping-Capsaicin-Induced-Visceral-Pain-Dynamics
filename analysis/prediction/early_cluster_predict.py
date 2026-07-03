"""
Subject-level temporal phenotype classification.

This module separates two related questions that were previously easy to
conflate:

1. Can baseline clinical/ECG/EGG features predict final DTW phenotypes?
2. Can early VAS dynamics classify a participant into the final phenotype?

The second task is useful for early classification, but it should be reported
separately from strictly pre-experiment phenotype prediction.
"""

from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVC

from analysis.data_loader import load_analysis_ready_baseline
from analysis.prediction.cluster_predict import (
    BASELINE_FEATURES,
    CATEGORICAL_FEATURES,
)

EXTRA_SIGNAL_FEATURES = [
    "mean_HR",
    "median_HR",
    "min_HR",
    "max_HR",
    "mean_RR",
    "median_RR",
    "min_RR",
    "max_RR",
    "total_power",
    "log_total_power",
]


def _vas_minute(col: str) -> int:
    match = re.search(r"(\d+)", col)
    return int(match.group(1)) if match else 10**6


def get_vas_columns(df: pd.DataFrame) -> List[str]:
    """Return VAS columns sorted by minute."""
    cols = [c for c in df.columns if c.startswith("VAS_") and "min" in c]
    return sorted(cols, key=_vas_minute)


def _clean_vas_prefix(df: pd.DataFrame, vas_cols: List[str]) -> pd.DataFrame:
    """
    Convert VAS values to numeric while respecting E/T censoring.

    Once an E/T marker appears in a row, subsequent VAS values are treated as
    unavailable for early classification.
    """
    cleaned = df[vas_cols].copy()
    for idx, row in cleaned.iterrows():
        for pos, val in enumerate(row):
            if str(val) in {"E", "T"}:
                cleaned.loc[idx, vas_cols[pos:]] = np.nan
                break
    return cleaned.apply(pd.to_numeric, errors="coerce")


def _safe_slope(row: pd.Series) -> float:
    valid = row.dropna().astype(float)
    if len(valid) < 2:
        return np.nan
    return float(np.polyfit(np.arange(len(valid)), valid.values, 1)[0])


def add_vas_prefix_features(
    X: pd.DataFrame,
    vas: pd.DataFrame,
    prefix_minutes: int,
    include_raw_vas: bool = True,
) -> pd.DataFrame:
    """
    Add raw and summary features from the first ``prefix_minutes`` VAS readings.
    """
    if prefix_minutes <= 0:
        return X

    use_cols = list(vas.columns[:prefix_minutes])
    if not use_cols:
        return X

    X = X.copy()
    prefix = vas[use_cols].astype(float)

    if include_raw_vas:
        for col in use_cols:
            X[col] = prefix[col]

    name = f"vas{len(use_cols)}"
    X[f"{name}_mean"] = prefix.mean(axis=1)
    X[f"{name}_max"] = prefix.max(axis=1)
    X[f"{name}_min"] = prefix.min(axis=1)
    X[f"{name}_last"] = prefix.iloc[:, -1]
    X[f"{name}_auc"] = prefix.sum(axis=1)
    X[f"{name}_range"] = X[f"{name}_max"] - X[f"{name}_min"]
    X[f"{name}_slope"] = prefix.apply(_safe_slope, axis=1)
    X[f"{name}_early_delta"] = prefix.iloc[:, -1] - prefix.iloc[:, 0]
    X[f"{name}_peak_time"] = prefix.apply(
        lambda row: int(np.nanargmax(row.values)) + 1 if row.notna().any() else np.nan,
        axis=1,
    )
    return X


def build_subject_classification_dataset(
    baseline_path: str,
    prefix_minutes: int = 8,
    include_baseline: bool = True,
    include_raw_vas: bool = True,
) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    """
    Build a subject-level dataset for cluster classification.

    ``prefix_minutes=0`` gives a strict baseline-only dataset. Positive values
    add early VAS trajectory features up to that minute.
    """
    df = load_analysis_ready_baseline(baseline_path)
    if "cluster" not in df.columns:
        raise ValueError("Expected a 'cluster' column in the baseline file.")

    y = df["cluster"].astype(int)

    if include_baseline:
        feature_cols = [
            c
            for c in BASELINE_FEATURES + EXTRA_SIGNAL_FEATURES
            if c in df.columns and c != "cluster"
        ]
        X = df[feature_cols].copy()
    else:
        X = pd.DataFrame(index=df.index)

    vas_cols = get_vas_columns(df)
    vas = _clean_vas_prefix(df, vas_cols)
    X = add_vas_prefix_features(
        X,
        vas,
        prefix_minutes=prefix_minutes,
        include_raw_vas=include_raw_vas,
    )

    return X, y, list(X.columns)


def _make_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    categorical = [
        c for c in X.columns if c in CATEGORICAL_FEATURES or X[c].dtype == object
    ]
    numeric = [c for c in X.columns if c not in categorical]

    return ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median")),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric,
            ),
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical,
            ),
        ],
    )


def make_subject_classification_models(random_state: int = 42) -> Dict[str, object]:
    """Return conservative candidate classifiers for small-N phenotype prediction."""
    return {
        "SparseLogistic": LogisticRegression(
            max_iter=3000,
            C=0.3,
            penalty="l1",
            solver="saga",
            class_weight="balanced",
            random_state=random_state,
        ),
        "LogisticRegression": LogisticRegression(
            max_iter=3000,
            C=0.3,
            class_weight="balanced",
            random_state=random_state,
        ),
        "SVM_RBF": SVC(
            kernel="rbf",
            C=1.0,
            gamma="scale",
            class_weight="balanced",
            random_state=random_state,
        ),
        "SVM_Linear": SVC(
            kernel="linear",
            C=0.3,
            class_weight="balanced",
            random_state=random_state,
        ),
        "RidgeClassifier": RidgeClassifier(class_weight="balanced"),
        "KNN_Distance": KNeighborsClassifier(n_neighbors=7, weights="distance"),
        "RandomForest": RandomForestClassifier(
            n_estimators=300,
            max_depth=4,
            min_samples_leaf=4,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=1,
        ),
        "ExtraTrees": ExtraTreesClassifier(
            n_estimators=300,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=1,
        ),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            max_iter=100,
            max_leaf_nodes=7,
            l2_regularization=1.0,
            random_state=random_state,
        ),
        "GaussianNB": GaussianNB(),
    }


def evaluate_subject_classifiers(
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int = 10,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Evaluate classifiers with strict out-of-fold predictions.

    Returns fold metrics, summary metrics, and aggregated confusion matrices.
    """
    labels = sorted(pd.Series(y).dropna().astype(int).unique())
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    preprocessor = _make_preprocessor(X)
    models = make_subject_classification_models(random_state=random_state)

    fold_rows = []
    cm_rows = []

    for model_name, estimator in models.items():
        y_pred_all = np.empty(len(y), dtype=int)

        for fold_idx, (train_idx, test_idx) in enumerate(cv.split(X, y)):
            pipe = Pipeline(
                [
                    ("prep", clone(preprocessor)),
                    ("clf", clone(estimator)),
                ]
            )
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

            pipe.fit(X_train, y_train)
            y_pred = pipe.predict(X_test).astype(int)
            y_pred_all[test_idx] = y_pred

            fold_rows.append(
                {
                    "model": model_name,
                    "fold": fold_idx,
                    "accuracy": accuracy_score(y_test, y_pred),
                    "balanced_accuracy": balanced_accuracy_score(y_test, y_pred),
                    "f1_macro": f1_score(
                        y_test, y_pred, average="macro", zero_division=0
                    ),
                    "f1_weighted": f1_score(
                        y_test, y_pred, average="weighted", zero_division=0
                    ),
                }
            )

        cm = confusion_matrix(y, y_pred_all, labels=labels)
        for i, true_label in enumerate(labels):
            for j, pred_label in enumerate(labels):
                cm_rows.append(
                    {
                        "model": model_name,
                        "true_cluster": int(true_label),
                        "predicted_cluster": int(pred_label),
                        "count": int(cm[i, j]),
                    }
                )

    fold_df = pd.DataFrame(fold_rows)
    summary = (
        fold_df.groupby("model", as_index=False)
        .agg(
            accuracy_mean=("accuracy", "mean"),
            accuracy_sd=("accuracy", "std"),
            balanced_accuracy_mean=("balanced_accuracy", "mean"),
            balanced_accuracy_sd=("balanced_accuracy", "std"),
            f1_macro_mean=("f1_macro", "mean"),
            f1_macro_sd=("f1_macro", "std"),
            f1_weighted_mean=("f1_weighted", "mean"),
            f1_weighted_sd=("f1_weighted", "std"),
        )
        .sort_values("balanced_accuracy_mean", ascending=False)
    )
    cm_df = pd.DataFrame(cm_rows)

    return fold_df, summary, cm_df


def run_subject_classification(
    baseline_path: str,
    output_dir: str,
    prefix_minutes: int = 8,
    n_splits: int = 10,
    random_state: int = 42,
) -> Dict[str, pd.DataFrame]:
    """Run and save subject classification for one early VAS prefix."""
    os.makedirs(output_dir, exist_ok=True)

    X, y, _ = build_subject_classification_dataset(
        baseline_path,
        prefix_minutes=prefix_minutes,
    )
    fold_df, summary_df, cm_df = evaluate_subject_classifiers(
        X,
        y,
        n_splits=n_splits,
        random_state=random_state,
    )

    stem = f"subject_classification_prefix_{prefix_minutes}min"
    fold_df.to_csv(os.path.join(output_dir, f"{stem}_fold_metrics.csv"), index=False)
    summary_df.to_csv(os.path.join(output_dir, f"{stem}_metrics.csv"), index=False)
    cm_df.to_csv(os.path.join(output_dir, f"{stem}_cm.csv"), index=False)

    return {"fold": fold_df, "metrics": summary_df, "cm": cm_df}


def compare_prefix_windows(
    baseline_path: str,
    output_dir: str,
    prefix_windows: Iterable[int] = (0, 3, 5, 8, 20),
    n_splits: int = 10,
    random_state: int = 42,
) -> pd.DataFrame:
    """Compare baseline-only and early-trajectory classification windows."""
    os.makedirs(output_dir, exist_ok=True)
    rows = []

    for prefix in prefix_windows:
        result = run_subject_classification(
            baseline_path,
            output_dir,
            prefix_minutes=prefix,
            n_splits=n_splits,
            random_state=random_state,
        )
        metrics = result["metrics"].copy()
        best = metrics.iloc[0].to_dict()
        best["prefix_minutes"] = prefix
        rows.append(best)

    comparison = pd.DataFrame(rows)
    comparison = comparison[
        [
            "prefix_minutes",
            "model",
            "accuracy_mean",
            "accuracy_sd",
            "balanced_accuracy_mean",
            "balanced_accuracy_sd",
            "f1_macro_mean",
            "f1_macro_sd",
            "f1_weighted_mean",
            "f1_weighted_sd",
        ]
    ]
    comparison.to_csv(
        os.path.join(output_dir, "subject_classification_window_comparison.csv"),
        index=False,
    )
    return comparison
