"""ECG/EGG-assisted phenotype classification."""

from __future__ import annotations

import os
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    RandomForestClassifier,
    StackingClassifier,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVC

from analysis.data_loader import ECG_EGG_FEATURE_COLUMNS, load_analysis_ready_baseline

CLINICAL_FEATURES = [
    "Sex",
    "Age",
    "BMI",
    "Height_cm",
    "Weight_kg",
    "CCEI",
    "AES",
    "Alcohol_consumption",
    "Spicy_food_frequency",
    "Usual_spiciness_level",
    "Spicy_food_preference",
    "Max_tolerable_spiciness",
    "Recent_spicy_intake_24h",
    "Spicy_episodes_24h",
    "Time_since_last_intake_h",
    "Baseline_GI_symptoms",
    "Time_since_last_meal_h",
]

CATEGORICAL_FEATURES = [
    "Sex",
    "Alcohol_consumption",
    "Recent_spicy_intake_24h",
    "Baseline_GI_symptoms",
]


def build_ecg_egg_cluster_dataset(baseline_path: str) -> Tuple[pd.DataFrame, pd.Series]:
    """Build phenotype classification features from clinical and ECG/EGG columns."""
    df = load_analysis_ready_baseline(baseline_path)
    if "cluster" not in df.columns:
        raise ValueError("Expected a 'cluster' column; run trajectory first.")

    feature_cols = [
        c for c in CLINICAL_FEATURES + ECG_EGG_FEATURE_COLUMNS if c in df.columns
    ]
    if not feature_cols:
        raise ValueError("No clinical or ECG/EGG feature columns are available.")

    y = pd.to_numeric(df["cluster"], errors="coerce")
    valid = y.notna()
    X = df.loc[valid, feature_cols].copy()
    y = y.loc[valid].astype(int)
    return X, y


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
        verbose_feature_names_out=False,
    )


def _make_models(random_state: int = 42) -> Dict[str, object]:
    return {
        "LogisticRegression": LogisticRegression(
            max_iter=3000,
            class_weight="balanced",
            random_state=random_state,
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=300,
            max_depth=5,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=1,
        ),
        "SVM_RBF": SVC(
            kernel="rbf",
            C=1.0,
            gamma="scale",
            class_weight="balanced",
            random_state=random_state,
        ),
        "MLP": MLPClassifier(
            hidden_layer_sizes=(64, 32),
            max_iter=1000,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=20,
            random_state=random_state,
        ),
        "Stacking": StackingClassifier(
            estimators=[
                (
                    "lr",
                    LogisticRegression(
                        max_iter=3000,
                        class_weight="balanced",
                        random_state=random_state,
                    ),
                ),
                (
                    "rf",
                    RandomForestClassifier(
                        n_estimators=200,
                        max_depth=5,
                        class_weight="balanced",
                        random_state=random_state,
                        n_jobs=1,
                    ),
                ),
                (
                    "svm",
                    SVC(
                        kernel="rbf",
                        class_weight="balanced",
                        random_state=random_state,
                    ),
                ),
            ],
            final_estimator=LogisticRegression(
                max_iter=3000,
                class_weight="balanced",
                random_state=random_state,
            ),
            cv=5,
            n_jobs=1,
        ),
    }


def _score(y_true: pd.Series, y_pred: np.ndarray) -> dict:
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
        "f1_macro": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "f1_weighted": f1_score(y_true, y_pred, average="weighted", zero_division=0),
    }


def run_ecg_egg_cluster_classification(
    baseline_path: str,
    output_dir: str,
    n_splits: int = 10,
    random_state: int = 42,
) -> dict[str, pd.DataFrame]:
    """Run strict out-of-fold ECG/EGG phenotype classification and save metrics."""
    os.makedirs(output_dir, exist_ok=True)
    X, y = build_ecg_egg_cluster_dataset(baseline_path)
    labels = sorted(y.unique())
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    preprocessor = _make_preprocessor(X)
    models = _make_models(random_state=random_state)

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
                {"model": model_name, "fold": fold_idx, **_score(y_test, y_pred)}
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
    summary_df = (
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
        .sort_values("accuracy_mean", ascending=False)
    )
    cm_df = pd.DataFrame(cm_rows)

    fold_df.to_csv(
        os.path.join(output_dir, "ecg_egg_cluster_prediction_fold_metrics.csv"),
        index=False,
    )
    summary_df.to_csv(
        os.path.join(output_dir, "ecg_egg_cluster_prediction_metrics.csv"),
        index=False,
    )
    cm_df.to_csv(
        os.path.join(output_dir, "ecg_egg_cluster_prediction_cm.csv"), index=False
    )

    fitted_preprocessor = clone(preprocessor).fit(X, y)
    X_processed = fitted_preprocessor.transform(X)
    feature_names = list(fitted_preprocessor.get_feature_names_out())

    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=5,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=1,
    )
    rf.fit(X_processed, y)
    rf_importance = pd.DataFrame(
        {"feature": feature_names, "importance": rf.feature_importances_}
    ).sort_values("importance", ascending=False)
    rf_importance.to_csv(
        os.path.join(output_dir, "ecg_egg_cluster_prediction_rf_importance.csv"),
        index=False,
    )

    lr = LogisticRegression(
        max_iter=3000,
        class_weight="balanced",
        random_state=random_state,
    )
    lr.fit(X_processed, y)
    lr_coef = pd.DataFrame(
        {
            "feature": feature_names,
            "abs_coef_mean": np.mean(np.abs(lr.coef_), axis=0),
        }
    ).sort_values("abs_coef_mean", ascending=False)
    lr_coef.to_csv(
        os.path.join(output_dir, "ecg_egg_cluster_prediction_lr_coef.csv"),
        index=False,
    )

    return {
        "fold": fold_df,
        "metrics": summary_df,
        "cm": cm_df,
        "rf_importance": rf_importance,
        "lr_coef": lr_coef,
    }
