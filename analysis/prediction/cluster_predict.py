"""
Predict cluster membership from baseline demographics and questionnaire scores.

Uses pre-experiment features (age, sex, BMI, spicy food habits, CCEI, AES, etc.)
to predict which temporal pain phenotype (cluster 0/1/2) a participant belongs to.
"""

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
    StackingClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import SVC

from analysis.data_loader import load_analysis_ready_baseline

CLUSTER_NAMES = {0: "Delayed-peak", 1: "Early-sustained", 2: "Late-rising"}

BASELINE_FEATURES = [
    # Demographics
    "Sex",
    "Age",
    "Height_cm",
    "Weight_kg",
    "BMI",
    # Spicy food habits
    "Alcohol_consumption",
    "Spicy_food_frequency",
    "Usual_spiciness_level",
    "Spicy_food_preference",
    "Max_tolerable_spiciness",
    # Capsaicin exposure indices
    "CCEI",
    "AES",
    # Recent intake
    "Recent_spicy_intake_24h",
    "Spicy_episodes_24h",
    "Time_since_last_intake_h",
    # Baseline symptoms
    "Baseline_GI_symptoms",
    # Timing
    "Time_since_last_meal_h",
    # ECG / HRV features
    "HR_sd",
    "HR_cv",
    "SDNN",
    "RMSSD",
    "pNN50",
    "pNN20",
    "CVSD",
    "LF_power",
    "HF_power",
    "LF_HF_ratio",
    "log_LF",
    "log_HF",
    "LFnu",
    "HFnu",
    "SD1",
    "SD2",
    "SD1_SD2_ratio",
    "ECG_SQI",
    "ECG_artifact_ratio",
    "ECG_RR_edit_ratio",
    # EGG features
    "dominant_freq_cpm",
    "mean_freq_cpm",
    "median_freq_cpm",
    "dominant_power",
    "total_power_egg",
    "log_DP",
    "log_total_power_egg",
    "pct_normogastria",
    "pct_bradygastria",
    "pct_tachygastria",
    "power_ratio",
    "spectral_entropy",
    "spectral_flatness",
    "DF_instability",
    "egg_signal_energy",
    "egg_rms",
    "EGG_SQI",
    "EGG_artifact_ratio",
    # ECG-EGG coupling
    "hr_egg_correlation",
    "ecg_egg_cross_corr_max",
    "ecg_egg_lag",
    "ecg_egg_coherence_mean",
    "ecg_egg_energy_ratio",
]

CATEGORICAL_FEATURES = [
    "Sex",
    "Alcohol_consumption",
    "Recent_spicy_intake_24h",
    "Baseline_GI_symptoms",
]


def load_baseline_data(baseline_path: str) -> pd.DataFrame:
    """Load baseline data and keep only relevant features + cluster label."""
    df = load_analysis_ready_baseline(baseline_path)
    cols = BASELINE_FEATURES + ["cluster", "ID"]
    cols = [c for c in cols if c in df.columns]
    return df[cols].copy()


def encode_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, LabelEncoder]]:
    """One-hot encode categorical features, leave numeric as-is."""
    encoders = {}
    frames = []

    for col in df.columns:
        if col in CATEGORICAL_FEATURES:
            le = LabelEncoder()
            encoded = le.fit_transform(df[col].astype(str))
            encoders[col] = le
            # One-hot
            ohe = pd.get_dummies(encoded, prefix=col, dtype=int)
            frames.append(ohe)
        else:
            frames.append(df[[col]])

    result = pd.concat(frames, axis=1)
    return result, encoders


def build_cluster_prediction_dataset(
    baseline_path: str,
) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    """
    Build the full dataset for cluster prediction.

    Returns
    -------
    X_df : pd.DataFrame
        Feature matrix (encoded, ready for modeling).
    y : pd.Series
        Cluster labels (0, 1, 2).
    feature_names : list of str
        Names of the encoded features.
    """
    df = load_baseline_data(baseline_path)
    y = df["cluster"]
    X_raw = df.drop(columns=["cluster", "ID"])
    X_encoded, _ = encode_features(X_raw)

    # Fill NaN with median
    for col in X_encoded.columns:
        if X_encoded[col].isnull().any():
            X_encoded[col] = X_encoded[col].fillna(X_encoded[col].median())

    return X_encoded, y, list(X_encoded.columns)


def _make_models(random_state: int = 42) -> Dict[str, object]:
    """Return the candidate phenotype-prediction models."""
    return {
        "Logistic Regression": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=1000,
                        class_weight="balanced",
                        random_state=random_state,
                    ),
                ),
            ]
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=200,
            max_depth=5,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
        ),
        "Gradient Boosting": GradientBoostingClassifier(
            n_estimators=100,
            max_depth=3,
            random_state=random_state,
        ),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            max_iter=200,
            max_depth=5,
            random_state=random_state,
        ),
        "MLP": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    MLPClassifier(
                        hidden_layer_sizes=(64, 32),
                        max_iter=1000,
                        early_stopping=True,
                        validation_fraction=0.1,
                        n_iter_no_change=20,
                        random_state=random_state,
                    ),
                ),
            ]
        ),
        "Stacking": StackingClassifier(
            estimators=[
                (
                    "lr",
                    Pipeline(
                        [
                            ("scaler", StandardScaler()),
                            (
                                "clf",
                                LogisticRegression(
                                    max_iter=1000,
                                    class_weight="balanced",
                                    random_state=random_state,
                                ),
                            ),
                        ]
                    ),
                ),
                (
                    "rf",
                    RandomForestClassifier(
                        n_estimators=200,
                        max_depth=5,
                        class_weight="balanced",
                        random_state=random_state,
                        n_jobs=-1,
                    ),
                ),
                (
                    "svm",
                    Pipeline(
                        [
                            ("scaler", StandardScaler()),
                            (
                                "clf",
                                SVC(
                                    kernel="rbf",
                                    class_weight="balanced",
                                    random_state=random_state,
                                ),
                            ),
                        ]
                    ),
                ),
                (
                    "hgb",
                    HistGradientBoostingClassifier(
                        max_iter=200,
                        max_depth=5,
                        random_state=random_state,
                    ),
                ),
            ],
            final_estimator=LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                random_state=random_state,
            ),
            cv=5,
            n_jobs=-1,
        ),
    }


def evaluate_cluster_prediction(
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int = 10,
    random_state: int = 42,
) -> Dict:
    """
    Evaluate multiple classifiers for cluster prediction using stratified CV.
    """
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    models = _make_models(random_state=random_state)

    results = {}

    for name, model in models.items():
        scoring = ["accuracy", "balanced_accuracy", "f1_macro", "f1_weighted"]
        cv_results = cross_validate(
            model,
            X,
            y,
            cv=cv,
            scoring=scoring,
            return_train_score=False,
        )
        results[name] = {
            "accuracy_mean": cv_results["test_accuracy"].mean(),
            "accuracy_sd": cv_results["test_accuracy"].std(),
            "balanced_accuracy_mean": cv_results["test_balanced_accuracy"].mean(),
            "balanced_accuracy_sd": cv_results["test_balanced_accuracy"].std(),
            "f1_macro_mean": cv_results["test_f1_macro"].mean(),
            "f1_macro_sd": cv_results["test_f1_macro"].std(),
            "f1_weighted_mean": cv_results["test_f1_weighted"].mean(),
            "f1_weighted_sd": cv_results["test_f1_weighted"].std(),
        }

    return results


def run_cluster_prediction(
    baseline_path: str,
    output_dir: str,
    n_splits: int = 10,
    random_state: int = 42,
) -> Dict:
    """
    Full pipeline: load data, evaluate models, save results.

    Returns results dict.
    """
    import os

    X, y, feature_names = build_cluster_prediction_dataset(baseline_path)

    print(f"Dataset: {X.shape[0]} samples, {X.shape[1]} features")
    print("Cluster distribution:")
    for c in sorted(y.unique()):
        n = (y == c).sum()
        print(f"  Cluster {c} ({CLUSTER_NAMES.get(c, 'Unknown')}): n={n}")

    results = evaluate_cluster_prediction(
        X, y, n_splits=n_splits, random_state=random_state
    )

    # Save metrics
    os.makedirs(output_dir, exist_ok=True)
    rows = []
    for model_name, metrics in results.items():
        rows.append({"model": model_name, **metrics})
    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(
        os.path.join(output_dir, "cluster_prediction_metrics.csv"), index=False
    )
    print(f"\nSaved: {os.path.join(output_dir, 'cluster_prediction_metrics.csv')}")

    # Save fold-level metrics for more detailed analysis
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    models = _make_models(random_state=random_state)

    fold_rows = []
    for model_name, model in models.items():
        for fold_idx, (train_idx, test_idx) in enumerate(cv.split(X, y)):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)

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

    fold_df = pd.DataFrame(fold_rows)
    fold_df.to_csv(
        os.path.join(output_dir, "cluster_prediction_fold_metrics.csv"), index=False
    )

    # Save confusion matrices (aggregated across folds)
    cm_records = []
    for model_name, model in models.items():
        y_pred_all = np.zeros_like(y.values)
        for fold_idx, (train_idx, test_idx) in enumerate(cv.split(X, y)):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
            model.fit(X_train, y_train)
            y_pred_all[test_idx] = model.predict(X_test)

        cm = confusion_matrix(y, y_pred_all, labels=[0, 1, 2])
        for i in range(3):
            for j in range(3):
                cm_records.append(
                    {
                        "model": model_name,
                        "true_cluster": i,
                        "predicted_cluster": j,
                        "count": int(cm[i, j]),
                    }
                )

    cm_df = pd.DataFrame(cm_records)
    cm_df.to_csv(os.path.join(output_dir, "cluster_prediction_cm.csv"), index=False)

    # Save feature importance for best model (Logistic Regression as primary)
    lr_model = models["Logistic Regression"]
    # Need to fit on all data to get coefficients
    lr_model.fit(X, y)
    lr_coef = lr_model.named_steps["clf"].coef_

    coef_records = []
    for cluster_idx in range(3):
        for feat_idx, feat_name in enumerate(feature_names):
            coef_records.append(
                {
                    "cluster": cluster_idx,
                    "feature": feat_name,
                    "coefficient": float(lr_coef[cluster_idx, feat_idx]),
                    "abs_coefficient": float(np.abs(lr_coef[cluster_idx, feat_idx])),
                }
            )

    coef_df = pd.DataFrame(coef_records)
    coef_df.to_csv(
        os.path.join(output_dir, "cluster_prediction_feature_coef.csv"), index=False
    )

    # Print summary
    print("\n" + "=" * 60)
    print("Cluster Prediction Results Summary")
    print("=" * 60)
    for model_name, m in results.items():
        print(f"\n{model_name}:")
        acc = f"{m['accuracy_mean']:.3f} +/- {m['accuracy_sd']:.3f}"
        bal = f"{m['balanced_accuracy_mean']:.3f} +/- {m['balanced_accuracy_sd']:.3f}"
        macro = f"{m['f1_macro_mean']:.3f} +/- {m['f1_macro_sd']:.3f}"
        weighted = f"{m['f1_weighted_mean']:.3f} +/- {m['f1_weighted_sd']:.3f}"
        print(f"  Accuracy:           {acc}")
        print(f"  Balanced Accuracy:  {bal}")
        print(f"  Macro F1:           {macro}")
        print(f"  Weighted F1:        {weighted}")

    return results
