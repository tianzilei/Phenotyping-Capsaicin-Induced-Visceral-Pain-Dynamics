"""
Regression models for VAS prediction: Ridge, MixedLM.
"""

from typing import Dict, Tuple

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold

from analysis.prediction.common import make_feature_cols, prepare_modeling_data


def calc_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """
    Compute regression metrics.

    Parameters
    ----------
    y_true : np.ndarray
        True values.
    y_pred : np.ndarray
        Predicted values.

    Returns
    -------
    dict
        Dictionary with MAE, RMSE, R2, Pearson r, p-value.
    """
    r, p = pearsonr(y_true, y_pred) if len(y_true) > 1 else (0.0, 1.0)
    return {
        "MAE": mean_absolute_error(y_true, y_pred),
        "RMSE": np.sqrt(mean_squared_error(y_true, y_pred)),
        "R2": r2_score(y_true, y_pred),
        "Pearson_r": r,
        "Pearson_p": p,
    }


def evaluate_regression_models(
    data: pd.DataFrame,
    y_col: str = "target",
    n_splits: int = 5,
    ridge_alpha: float = 1.0,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Evaluate regression models using GroupKFold cross-validation.

    Parameters
    ----------
    data : pd.DataFrame
        Supervised dataset.
    y_col : str
        Target column name.
    n_splits : int
        Number of CV folds.
    ridge_alpha : float
        Ridge regression alpha parameter.

    Returns
    -------
    tuple of (pd.DataFrame, pd.DataFrame, pd.DataFrame)
        (fold_metrics, summary_metrics, all_predictions)
    """
    data = prepare_modeling_data(data)
    feature_cols = make_feature_cols(data)

    X = data[feature_cols].values
    y = data[y_col].values
    groups = data["subject_id"].values

    gkf = GroupKFold(n_splits=n_splits)

    fold_metrics = []
    all_preds = []

    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        # Ridge regression
        model = Ridge(alpha=ridge_alpha)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        metrics = calc_metrics(y_test, y_pred)
        metrics["fold"] = fold + 1
        fold_metrics.append(metrics)

        # Store predictions
        pred_df = data.iloc[test_idx].copy()
        pred_df["predicted"] = y_pred
        pred_df["fold"] = fold + 1
        all_preds.append(pred_df)

    fold_df = pd.DataFrame(fold_metrics)
    summary = fold_df.mean(numeric_only=True).to_frame().T
    summary.index = ["mean"]

    all_predictions = pd.concat(all_preds, ignore_index=True)

    return fold_df, summary, all_predictions


def get_ridge_coefficients(
    data: pd.DataFrame,
    y_col: str = "target",
    alpha: float = 1.0,
) -> pd.DataFrame:
    """
    Fit Ridge regression on full data and return coefficients.

    Parameters
    ----------
    data : pd.DataFrame
        Supervised dataset.
    y_col : str
        Target column name.
    alpha : float
        Ridge alpha parameter.

    Returns
    -------
    pd.DataFrame
        Coefficients DataFrame sorted by absolute value.
    """
    data = prepare_modeling_data(data)
    feature_cols = make_feature_cols(data)

    X = data[feature_cols].values
    y = data[y_col].values

    model = Ridge(alpha=alpha)
    model.fit(X, y)

    coef_df = pd.DataFrame({"feature": feature_cols, "coefficient": model.coef_})
    coef_df["abs_coef"] = coef_df["coefficient"].abs()
    coef_df = coef_df.sort_values("abs_coef", ascending=False)

    return coef_df
