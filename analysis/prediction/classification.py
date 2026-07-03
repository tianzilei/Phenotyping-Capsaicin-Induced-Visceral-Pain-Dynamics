"""
Classification models for VAS direction prediction: Baselines and Logistic Regression.
"""

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from analysis.prediction.common import prepare_modeling_data


class MajorityClassifier(BaseEstimator, ClassifierMixin):
    """
    Baseline classifier that always predicts the most frequent class.

    This classifier ignores input features and predicts the majority class
    from the training set for all samples.
    """

    def __init__(self):
        self.majority_class_ = None
        self.classes_ = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "MajorityClassifier":
        """
        Fit the classifier by finding the most frequent class.

        Parameters
        ----------
        X : np.ndarray
            Feature matrix (ignored).
        y : np.ndarray
            Target labels.

        Returns
        -------
        MajorityClassifier
            Fitted classifier.
        """
        unique, counts = np.unique(y, return_counts=True)
        self.majority_class_ = unique[np.argmax(counts)]
        self.classes_ = unique
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict the majority class for all samples.

        Parameters
        ----------
        X : np.ndarray
            Feature matrix (ignored).

        Returns
        -------
        np.ndarray
            Array of predictions (majority class repeated).
        """
        n_samples = X.shape[0] if X.ndim > 1 else len(X)
        return np.full(n_samples, self.majority_class_)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Predict class probabilities (1.0 for majority class).

        Parameters
        ----------
        X : np.ndarray
            Feature matrix (ignored).

        Returns
        -------
        np.ndarray
            Probability array of shape (n_samples, n_classes).
        """
        n_samples = X.shape[0] if X.ndim > 1 else len(X)
        proba = np.zeros((n_samples, len(self.classes_)))
        idx = np.where(self.classes_ == self.majority_class_)[0][0]
        proba[:, idx] = 1.0
        return proba


class PersistenceDirectionClassifier(BaseEstimator, ClassifierMixin):
    """
    Baseline classifier that predicts decrease based on current slope.

    If the current slope is strongly negative, predicts decrease (1).
    Otherwise predicts non-decrease (0).
    """

    def __init__(self, slope_idx: int = -1):
        self.slope_idx = slope_idx
        self.classes_ = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "PersistenceDirectionClassifier":
        """
        Fit the classifier (stores unique classes).

        Parameters
        ----------
        X : np.ndarray
            Feature matrix (ignored).
        y : np.ndarray
            Target labels.

        Returns
        -------
        PersistenceDirectionClassifier
            Fitted classifier.
        """
        self.classes_ = np.unique(y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict decrease based on the slope feature.

        Parameters
        ----------
        X : np.ndarray
            Feature matrix. Column at ``slope_idx`` is assumed to be slope.

        Returns
        -------
        np.ndarray
            Predicted labels: 1 (decrease) or 0 (non-decrease).
        """
        if X.ndim == 1:
            slope = X[self.slope_idx]
        else:
            slope = X[:, self.slope_idx]

        predictions = np.where(slope < -0.1, 1, 0)
        return predictions

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Predict class probabilities (1.0 for predicted class).

        Parameters
        ----------
        X : np.ndarray
            Feature matrix.

        Returns
        -------
        np.ndarray
            Probability array of shape (n_samples, n_classes).
        """
        preds = self.predict(X)
        n_classes = len(self.classes_)
        proba = np.zeros((len(preds), n_classes))
        for i, pred in enumerate(preds):
            idx = np.where(self.classes_ == pred)[0]
            if len(idx) > 0:
                proba[i, idx[0]] = 1.0
        return proba


def encode_direction(delta: float) -> int:
    """
    Encode VAS change as direction class.

    Parameters
    ----------
    delta : float
        Change in VAS.

    Returns
    -------
    int
        -1 (decrease), 0 (no change), 1 (increase).
    """
    if delta > 0.1:
        return 1
    elif delta < -0.1:
        return -1
    else:
        return 0


def build_direction_dataset(
    df: pd.DataFrame,
    time_cols: List[str],
    window: int = 3,
    target_mode: str = "direction",
    include_cluster: bool = False,
    include_phenotype: bool = True,
) -> Tuple[pd.DataFrame, str]:
    """
    Build supervised dataset with direction labels.

    Parameters
    ----------
    df : pd.DataFrame
        Raw VAS DataFrame.
    time_cols : list of str
        Time column names.
    window : int
        Sliding window size.
    target_mode : str
        'direction3' for -1/0/+1, 'direction' for binary up/down.
    include_cluster : bool
        Whether to include an externally provided cluster as a feature.
    include_phenotype : bool
        Whether to include causal subject-level summary features computed
        only from observations available up to the current time point.

    Returns
    -------
    tuple of (pd.DataFrame, str)
        Supervised DataFrame and target column name.
    """
    from analysis.prediction.common import clean_time_series

    records = []

    for _, row in df.iterrows():
        subject_id = row.get("ID", row.name)

        raw_vals = row[time_cols]
        vals = clean_time_series(raw_vals)
        vals_list = vals.values.tolist()

        for i in range(window, len(vals_list) - 1):
            feature_vals = vals_list[i - window : i]
            if any(np.isnan(v) for v in feature_vals):
                continue

            current = vals_list[i]
            if np.isnan(current):
                continue

            next_val = vals_list[i + 1]
            if np.isnan(next_val):
                continue

            record = {
                "subject_id": subject_id,
                "time_idx": i,
            }

            # Lag features
            for j in range(window):
                record[f"lag_{j + 1}"] = feature_vals[j]

            record["current_vas"] = current

            # Extended features
            record["window_mean"] = np.mean(feature_vals)
            record["window_std"] = np.std(feature_vals)
            record["window_max"] = np.max(feature_vals)
            record["window_min"] = np.min(feature_vals)
            record["window_range"] = record["window_max"] - record["window_min"]
            record["slope"] = np.polyfit(range(window), feature_vals, 1)[0]
            record["monotonic_up"] = sum(
                1
                for j in range(1, len(feature_vals))
                if feature_vals[j] > feature_vals[j - 1]
            )
            record["monotonic_down"] = sum(
                1
                for j in range(1, len(feature_vals))
                if feature_vals[j] < feature_vals[j - 1]
            )

            # Time index as a feature (normalized to 0-1 range over 20 minutes)
            record["time_idx_feature"] = i / max(len(vals_list) - 1, 1)

            history = vals.iloc[: i + 1].dropna()
            history_len = len(history)
            running_max = history.max() if history_len else current
            running_min = history.min() if history_len else current
            max_positions = history.index[history == running_max]
            min_positions = history.index[history == running_min]
            if len(max_positions) > 0:
                last_max_pos = vals.index.get_loc(max_positions[-1])
                record["steps_since_running_max"] = i - last_max_pos
            else:
                record["steps_since_running_max"] = 0
            if len(min_positions) > 0:
                last_min_pos = vals.index.get_loc(min_positions[-1])
                record["steps_since_running_min"] = i - last_min_pos
            else:
                record["steps_since_running_min"] = 0
            record["gap_to_running_max"] = running_max - current
            record["gap_from_running_min"] = current - running_min

            # Subject-level features restricted to information available so far
            if include_phenotype:
                record["avg_vas_so_far"] = history.mean() if history_len else current
                record["vas_sd_so_far"] = history.std(ddof=0) if history_len > 1 else 0.0
                record["running_range_so_far"] = running_max - running_min

            if include_cluster and "cluster" in df.columns:
                record["cluster"] = row["cluster"]

            # Target
            delta = next_val - current
            if target_mode == "direction3":
                record["target"] = encode_direction(delta)
                target_col = "target"
            elif target_mode == "direction":
                record["target"] = 1 if delta < 0 else 0
                target_col = "target"
            else:
                raise ValueError(f"Unknown target_mode: {target_mode}")

            records.append(record)

    return pd.DataFrame(records), target_col


def compute_classification_metrics(
    y_true: np.ndarray, y_pred: np.ndarray
) -> Dict[str, float]:
    """
    Compute classification metrics.

    Parameters
    ----------
    y_true : np.ndarray
        True labels.
    y_pred : np.ndarray
        Predicted labels.

    Returns
    -------
    dict
        Dictionary with accuracy, balanced_accuracy, f1_macro, f1_weighted.
    """
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
        "f1_macro": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "f1_weighted": f1_score(y_true, y_pred, average="weighted", zero_division=0),
    }


def evaluate_classification_models(
    data: pd.DataFrame,
    y_col: str = "target",
    n_splits: int = 5,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
    """
    Evaluate classification models using GroupKFold cross-validation.

    Evaluates three models: MajorityClassifier, PersistenceDirectionClassifier,
    and Logistic Regression with class balancing.

    Parameters
    ----------
    data : pd.DataFrame
        Supervised dataset.
    y_col : str
        Target column name.
    n_splits : int
        Number of CV folds.

    Returns
    -------
    tuple of (pd.DataFrame, pd.DataFrame, pd.DataFrame, dict)
        (fold_metrics, summary_metrics, all_predictions, confusion_matrices)
    """
    data = prepare_modeling_data(data)

    # One-hot encode cluster if present
    if "cluster" in data.columns:
        data = pd.get_dummies(
            data, columns=["cluster"], prefix="cluster", drop_first=True
        )

    feature_cols = [
        col for col in data.columns if col not in {"subject_id", "time_idx", "target"}
    ]
    X = data[feature_cols].values
    y = data[y_col].values
    groups = data["subject_id"].values

    gkf = GroupKFold(n_splits=n_splits)

    # Locate slope index for persistence baseline by column name
    slope_idx = feature_cols.index("slope") if "slope" in feature_cols else -1

    # Define models
    models = {
        "Majority": MajorityClassifier(),
        "PersistenceDir": PersistenceDirectionClassifier(slope_idx=slope_idx),
        "Logistic": make_pipeline(
            StandardScaler(),
            LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                random_state=42,
                solver="liblinear",
            ),
        ),
    }

    fold_metrics = []
    all_preds = []
    all_cms = {}

    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        # Handle NaN
        X_train = np.nan_to_num(X_train)
        X_test = np.nan_to_num(X_test)

        for model_name, model in models.items():
            # Fit model
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)

            # Compute metrics
            metrics = compute_classification_metrics(y_test, y_pred)
            metrics["fold"] = fold + 1
            metrics["model"] = model_name
            fold_metrics.append(metrics)

            # Confusion matrix
            cm = confusion_matrix(y_test, y_pred, labels=sorted(np.unique(y)))
            all_cms[f"{model_name}_fold_{fold + 1}"] = cm

            # Store predictions
            pred_df = data.iloc[test_idx].copy()
            pred_df["predicted"] = y_pred
            pred_df["fold"] = fold + 1
            pred_df["model"] = model_name
            all_preds.append(pred_df)

    fold_df = pd.DataFrame(fold_metrics)
    summary = fold_df.groupby("model").mean(numeric_only=True)
    summary.index.name = "model"
    summary = summary.reset_index()

    all_predictions = pd.concat(all_preds, ignore_index=True)

    return fold_df, summary, all_predictions, all_cms
