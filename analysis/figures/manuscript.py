#!/usr/bin/env python3
"""Generate standalone manuscript figures with seaborn."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from analysis.constants import FIGURES_DIR, METRICS_DIR, REGION_CODE_MAP, SYMPTOM_CODE_MAP
from analysis.data_loader import get_vas_columns, load_analysis_ready_baseline
from analysis.parsing import map_codes, parse_compact_codes, parse_region_codes
from analysis.trajectory.clustering import prepare_vas_data
from analysis.trajectory.shapelets import extract_shapelets
from analysis.visualization.style import set_publication_style

PALETTE_NAME = "magma"
PALETTE = sns.color_palette(PALETTE_NAME, n_colors=8)
CLUSTER_PALETTE = {0: PALETTE[1], 1: PALETTE[3], 2: PALETTE[5]}
CLUSTER_NAMES = {0: "Delayed-peak", 1: "Early-sustained", 2: "Late-rising"}
_BASELINE_SOURCE_PATH: str | None = None
_METRICS_SOURCE_DIR = METRICS_DIR


def configure_sources(
    baseline_path: str | None = None,
    metrics_dir: str = METRICS_DIR,
) -> None:
    """Configure the baseline file and metrics directory used by figure builders."""
    global _BASELINE_SOURCE_PATH, _METRICS_SOURCE_DIR
    _BASELINE_SOURCE_PATH = baseline_path
    _METRICS_SOURCE_DIR = metrics_dir


def _ensure_dir(path: str) -> str:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    return path


def _save(fig: plt.Figure, output_path: str) -> None:
    _ensure_dir(output_path)
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Saved: {output_path}")


def _no_data(ax: plt.Axes, title: str) -> None:
    ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
    ax.set_title(title, fontweight="bold")
    ax.set_axis_off()


def clean_figure_outputs(output_dir: str = FIGURES_DIR) -> None:
    """Remove old manuscript PNG outputs."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for png in out.glob("*.png"):
        png.unlink()
    supp = out / "supplement"
    if supp.exists():
        shutil.rmtree(supp)


def _time_from_vas_col(col: str) -> int:
    return int(col.replace("VAS_", "").replace("min", ""))


def _load_baseline() -> tuple[pd.DataFrame, list[str]]:
    df = load_analysis_ready_baseline(_BASELINE_SOURCE_PATH)
    vas_cols = sorted(get_vas_columns(df), key=_time_from_vas_col)
    return df, vas_cols


def _vas_long(df: pd.DataFrame, vas_cols: list[str]) -> pd.DataFrame:
    id_vars = ["ID"] + (["cluster"] if "cluster" in df.columns else [])
    long_df = df.melt(
        id_vars=id_vars, value_vars=vas_cols, var_name="time", value_name="VAS"
    )
    long_df["VAS"] = pd.to_numeric(long_df["VAS"], errors="coerce")
    long_df = long_df.dropna(subset=["VAS"])
    long_df["time_min"] = long_df["time"].map(_time_from_vas_col)
    if "cluster" in long_df.columns:
        long_df["cluster"] = pd.to_numeric(long_df["cluster"], errors="coerce")
        long_df["phenotype"] = long_df["cluster"].map(CLUSTER_NAMES)
    return long_df


def _read_metric(name: str) -> pd.DataFrame | None:
    path = Path(_METRICS_SOURCE_DIR) / name
    if not path.exists():
        return None
    return pd.read_csv(path)


def _top_matrix(name: str, n_rows: int = 8, n_cols: int = 8) -> pd.DataFrame | None:
    df = _read_metric(name)
    if df is None or df.empty:
        return None
    df = df.set_index(df.columns[0]).apply(pd.to_numeric, errors="coerce").fillna(0)
    rows = df.sum(axis=1).sort_values(ascending=False).head(n_rows).index
    cols = df.sum(axis=0).sort_values(ascending=False).head(n_cols).index
    return df.loc[rows, cols]


def _code_summary(
    df: pd.DataFrame,
    source_col: str,
    parser,
    code_map: dict,
    top_n: int = 8,
) -> pd.DataFrame:
    rows = []
    if source_col not in df.columns:
        return pd.DataFrame(columns=["label", "n", "percent"])
    for _, row in df.iterrows():
        codes = parser(str(row.get(source_col, "")), valid_codes=set(code_map.keys()))
        for label in map_codes(codes, code_map):
            rows.append({"ID": row["ID"], "label": label})
    if not rows:
        return pd.DataFrame(columns=["label", "n", "percent"])
    out = (
        pd.DataFrame(rows)
        .drop_duplicates(["ID", "label"])
        .groupby("label", as_index=False)
        .size()
        .rename(columns={"size": "n"})
        .sort_values("n", ascending=False)
        .head(top_n)
    )
    out["percent"] = out["n"] / len(df) * 100
    return out


def _cluster_legend(ax: plt.Axes, values: pd.Series) -> None:
    handles, _ = ax.get_legend_handles_labels()
    clusters = sorted(pd.to_numeric(values, errors="coerce").dropna().astype(int).unique())
    ax.legend(handles, [CLUSTER_NAMES.get(c, f"Cluster {c}") for c in clusters], title="Phenotype")


def generate_figure1(output_path: str) -> None:
    """Figure 1: group mean VAS trajectory."""
    print("Generating Figure 1: group mean VAS trajectory...")
    df, vas_cols = _load_baseline()
    long_df = _vas_long(df, vas_cols)
    fig, ax = plt.subplots(figsize=(8, 6))

    sns.lineplot(
        data=long_df,
        x="time_min",
        y="VAS",
        estimator="mean",
        errorbar="se",
        marker="o",
        color=PALETTE[2],
        ax=ax,
    )
    ax.set_title("Group Mean VAS Trajectory", fontweight="bold")
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("VAS")
    _save(fig, output_path)


def generate_figure2(output_path: str) -> None:
    """Figure 2: phenotype-specific VAS trajectories."""
    print("Generating Figure 2: phenotype trajectories...")
    df, vas_cols = _load_baseline()
    long_df = _vas_long(df, vas_cols)
    fig, ax = plt.subplots(figsize=(8, 6))

    if "cluster" in long_df.columns:
        sns.lineplot(
            data=long_df,
            x="time_min",
            y="VAS",
            hue="cluster",
            estimator="mean",
            errorbar="se",
            marker="o",
            palette=CLUSTER_PALETTE,
            ax=ax,
        )
        _cluster_legend(ax, long_df["cluster"])
    else:
        _no_data(ax, "Phenotype Trajectories")
    ax.set_title("Phenotype-Specific VAS Trajectories", fontweight="bold")
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("VAS")
    _save(fig, output_path)


def generate_figure3(output_path: str) -> None:
    """Figure 3: symptom burden."""
    print("Generating Figure 3: symptom burden...")
    df, _ = _load_baseline()
    fig, ax = plt.subplots(figsize=(8, 6))

    symptom = _code_summary(df, "Symptom_codes", parse_compact_codes, SYMPTOM_CODE_MAP)
    if symptom.empty:
        _no_data(ax, "Symptom Burden")
    else:
        sns.barplot(
            data=symptom,
            x="percent",
            y="label",
            hue="label",
            palette=PALETTE_NAME,
            legend=False,
            ax=ax,
        )
        ax.set_title("Symptom Burden", fontweight="bold")
        ax.set_xlabel("Participants (%)")
        ax.set_ylabel("")
    _save(fig, output_path)


def generate_figure4(output_path: str) -> None:
    """Figure 4: pain region burden."""
    print("Generating Figure 4: pain region burden...")
    df, _ = _load_baseline()
    fig, ax = plt.subplots(figsize=(8, 6))

    region = _code_summary(df, "Region_code", parse_region_codes, REGION_CODE_MAP)
    if region.empty:
        _no_data(ax, "Pain Region Burden")
    else:
        sns.barplot(
            data=region,
            x="percent",
            y="label",
            hue="label",
            palette=PALETTE_NAME,
            legend=False,
            ax=ax,
        )
        ax.set_title("Pain Region Burden", fontweight="bold")
        ax.set_xlabel("Participants (%)")
        ax.set_ylabel("")
    _save(fig, output_path)


def generate_figure5(output_path: str) -> None:
    """Figure 5: early VAS window classification."""
    print("Generating Figure 5: early VAS window classification...")
    fig, ax = plt.subplots(figsize=(8, 6))

    windows = _read_metric("subject_classification_window_comparison.csv")
    if windows is None or windows.empty:
        _no_data(ax, "Early Window Phenotype Classification")
    else:
        sns.lineplot(
            data=windows,
            x="prefix_minutes",
            y="accuracy_mean",
            marker="o",
            color=PALETTE[4],
            ax=ax,
        )
        ax.fill_between(
            windows["prefix_minutes"],
            windows["accuracy_mean"] - windows["accuracy_sd"],
            windows["accuracy_mean"] + windows["accuracy_sd"],
            color=PALETTE[4],
            alpha=0.18,
        )
        ax.set_title("Early VAS Window Classification", fontweight="bold")
        ax.set_xlabel("Prefix window (min)")
        ax.set_ylabel("Accuracy")
    _save(fig, output_path)


def generate_figure6(output_path: str) -> None:
    """Figure 6: phenotype prediction from baseline and physiology."""
    print("Generating Figure 6: baseline and physiology prediction...")
    fig, ax = plt.subplots(figsize=(8, 6))

    cluster_pred = _read_metric("cluster_prediction_metrics.csv")
    if cluster_pred is None or cluster_pred.empty:
        _no_data(ax, "Phenotype Prediction")
    else:
        plot_df = cluster_pred.sort_values("accuracy_mean", ascending=False)
        sns.barplot(
            data=plot_df,
            x="accuracy_mean",
            y="model",
            hue="model",
            palette=PALETTE_NAME,
            legend=False,
            ax=ax,
        )
        ax.set_title("Baseline/Physiology Phenotype Prediction", fontweight="bold")
        ax.set_xlabel("Accuracy")
        ax.set_ylabel("")
    _save(fig, output_path)


def generate_figure7(output_path: str) -> None:
    """Figure 7: age distribution by phenotype."""
    print("Generating Figure 7: age by phenotype...")
    df, _ = _load_baseline()
    df = df.copy()
    if "cluster" in df.columns:
        df["cluster"] = pd.to_numeric(df["cluster"], errors="coerce")
        df["phenotype"] = df["cluster"].map(CLUSTER_NAMES)
    fig, ax = plt.subplots(figsize=(8, 6))

    if "phenotype" in df.columns and "Age" in df.columns:
        sns.boxplot(
            data=df,
            x="phenotype",
            y="Age",
            hue="phenotype",
            palette=list(CLUSTER_PALETTE.values()),
            legend=False,
            ax=ax,
        )
        ax.set_title("Age by Phenotype", fontweight="bold")
        ax.set_xlabel("")
        ax.set_ylabel("Age")
    else:
        _no_data(ax, "Age by Phenotype")
    _save(fig, output_path)


def generate_figure8(output_path: str) -> None:
    """Figure 8: standardized ECG/EGG features."""
    print("Generating Figure 8: standardized ECG/EGG features...")
    df, _ = _load_baseline()
    df = df.copy()
    if "cluster" in df.columns:
        df["cluster"] = pd.to_numeric(df["cluster"], errors="coerce")
        df["phenotype"] = df["cluster"].map(CLUSTER_NAMES)
    fig, ax = plt.subplots(figsize=(9, 6))

    phys_cols = [
        c
        for c in ["mean_HR", "SDNN", "LF_HF_ratio", "dominant_freq_cpm", "pct_normogastria"]
        if c in df.columns
    ]
    if "phenotype" in df.columns and phys_cols:
        phys = df.melt(
            id_vars="phenotype",
            value_vars=phys_cols,
            var_name="feature",
            value_name="value",
        ).dropna()
        phys["z_value"] = phys.groupby("feature")["value"].transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-8)
        )
        sns.boxplot(
            data=phys,
            x="feature",
            y="z_value",
            hue="phenotype",
            palette=list(CLUSTER_PALETTE.values()),
            ax=ax,
        )
        ax.set_title("Standardized ECG/EGG Features", fontweight="bold")
        ax.set_xlabel("")
        ax.set_ylabel("Z-score")
        ax.tick_params(axis="x", rotation=25)
    else:
        _no_data(ax, "Standardized ECG/EGG Features")

    _save(fig, output_path)


def generate_figure9(output_path: str) -> None:
    print("Generating Figure 9: onset timing...")
    cp = _read_metric("trajectory_change_points.csv")
    fig, ax = plt.subplots(figsize=(8, 6))
    if cp is None or cp.empty:
        _no_data(ax, "Onset and Change-Point Timing")
    else:
        cp_long = cp.melt(
            value_vars=[
                c for c in ["pain_onset_min", "pain_onset_derivative", "change_point_rank"] if c in cp.columns
            ],
            var_name="method",
            value_name="time_min",
        ).dropna()
        cp_long["method"] = cp_long["method"].map(
            {
                "pain_onset_min": "VAS > 3",
                "pain_onset_derivative": "Derivative",
                "change_point_rank": "PELT",
            }
        )
        sns.histplot(
            data=cp_long,
            x="time_min",
            hue="method",
            multiple="layer",
            bins=range(1, 22),
            palette=sns.color_palette(PALETTE_NAME, n_colors=3),
            alpha=0.55,
            ax=ax,
        )
        ax.set_title("Onset and Change-Point Timing", fontweight="bold")
        ax.set_xlabel("Time (min)")
        ax.set_ylabel("Participants")
    _save(fig, output_path)


def generate_figure10(output_path: str) -> None:
    print("Generating Figure 10: Kaplan-Meier event curves...")
    surv = _read_metric("trajectory_survival_data.csv")
    fig, ax = plt.subplots(figsize=(8, 6))
    if surv is None or surv.empty:
        _no_data(ax, "Kaplan-Meier Event Curves")
    else:
        from lifelines import KaplanMeierFitter

        curves = []
        for label, time_col, observed_col in [
            ("Onset", "onset_time", "onset_observed"),
            ("Relief", "relief_time", "relief_observed"),
        ]:
            kmf = KaplanMeierFitter()
            kmf.fit(surv[time_col], event_observed=surv[observed_col], label=label)
            sf = kmf.survival_function_.reset_index()
            sf.columns = ["time_min", "survival"]
            sf["event"] = label
            curves.append(sf)
        sns.lineplot(
            data=pd.concat(curves, ignore_index=True),
            x="time_min",
            y="survival",
            hue="event",
            palette=[PALETTE[2], PALETTE[5]],
            ax=ax,
        )
        ax.set_title("Kaplan-Meier Event Curves", fontweight="bold")
        ax.set_xlabel("Time (min)")
        ax.set_ylabel("Survival probability")
    _save(fig, output_path)


def generate_figure11(output_path: str) -> None:
    print("Generating Figure 11: cluster-specific shapelets...")
    df, vas_cols = _load_baseline()
    try:
        if "cluster" not in df.columns:
            raise ValueError("cluster labels are missing; run trajectory first")

        cluster_labels = pd.to_numeric(df["cluster"], errors="coerce")
        valid_mask = cluster_labels.notna()
        if not valid_mask.any():
            raise ValueError("cluster labels are empty; run trajectory first")

        df = df.loc[valid_mask].reset_index(drop=True)
        labels = cluster_labels.loc[valid_mask].astype(int).to_numpy()
        X, X_raw, _ = prepare_vas_data(df, vas_cols)
        n_clusters = len(np.unique(labels))
        shapelets = extract_shapelets(
            X_raw,
            labels,
            n_clusters=n_clusters,
            min_len=5,
            max_len=5,
            top_k=3,
        )
        shapelets = shapelets.sort_values(
            ["target_cluster", "auc", "cohens_d"],
            ascending=[True, False, False],
        ).reset_index(drop=True)
        n_clusters = int(shapelets["target_cluster"].nunique())
        top_k = int(shapelets.groupby("target_cluster").size().max())
        fig, axes = plt.subplots(
            n_clusters,
            top_k,
            figsize=(12.8, 7.4),
            sharex=True,
            sharey=True,
            constrained_layout=True,
        )
        axes = np.atleast_2d(axes)
        all_values = []
        for _, row in shapelets.iterrows():
            all_values.extend(
                [row[f"shapelet_pt{j}"] for j in range(1, int(row["length"]) + 1)]
            )
        y_min = min(all_values) - 0.2
        y_max = max(all_values) + 0.2
        total_time = len(vas_cols)

        panel_idx = 0
        for cluster_pos, target_cluster in enumerate(sorted(shapelets["target_cluster"].unique())):
            cluster_shapelets = (
                shapelets[shapelets["target_cluster"] == target_cluster]
                .sort_values(["auc", "cohens_d"], ascending=[False, False])
                .reset_index(drop=True)
            )
            phenotype_idx = int(target_cluster) - 1
            color = CLUSTER_PALETTE.get(phenotype_idx, PALETTE[cluster_pos])
            phenotype_name = CLUSTER_NAMES.get(
                phenotype_idx, f"Cluster {int(target_cluster)}"
            )

            for shapelet_pos in range(top_k):
                ax = axes[cluster_pos, shapelet_pos]
                if shapelet_pos >= len(cluster_shapelets):
                    ax.set_axis_off()
                    continue

                row = cluster_shapelets.iloc[shapelet_pos]
                shapelet_length = int(row["length"])
                shapelet_start = int(row["start"])
                source_subject = int(row["source_subject"])
                # `start` is zero-based on the original 20-minute trajectory.
                # Plot on the absolute post-capsaicin timeline rather than local
                # shapelet coordinates so the motif timing remains visible.
                x = np.arange(shapelet_start + 1, shapelet_start + shapelet_length + 1)
                y = np.array(
                    [row[f"shapelet_pt{j}"] for j in range(1, shapelet_length + 1)],
                    dtype=float,
                )
                full_x = np.arange(1, total_time + 1)
                full_y = np.asarray(X_raw[source_subject], dtype=float).reshape(-1)

                ax.plot(
                    full_x,
                    full_y,
                    color=color,
                    linewidth=1.7,
                    linestyle="--",
                    alpha=0.28,
                    zorder=1,
                )
                ax.plot(x, y, color=color, linewidth=2.8, marker="o", markersize=4.5, zorder=3)
                ax.fill_between(x, 0, y, color=color, alpha=0.08)
                ax.axhline(0, color="#b9b9b9", linewidth=0.8, linestyle="--", zorder=0)
                ax.grid(alpha=0.18, linewidth=0.7)
                ax.set_xlim(0, total_time)
                ax.set_ylim(y_min, y_max)
                ax.set_xticks([0, 5, 10, 15, 20])
                if cluster_pos == 0:
                    ax.set_title(
                        f"Top shapelet {shapelet_pos + 1}",
                        fontsize=11,
                        pad=10,
                        fontweight="bold",
                    )
                ax.text(
                    0.02,
                    0.97,
                    f"({chr(65 + panel_idx)})",
                    transform=ax.transAxes,
                    ha="left",
                    va="top",
                    fontsize=10,
                    fontweight="bold",
                )
                if shapelet_pos == 0:
                    ax.text(
                        0.11,
                        0.97,
                        phenotype_name,
                        transform=ax.transAxes,
                        ha="left",
                        va="top",
                        fontsize=11,
                        fontweight="bold",
                    )
                ax.text(
                    0.98,
                    0.97,
                    (
                        f"AUC {row['auc']:.3f}\n"
                        f"d {row['cohens_d']:.2f}\n"
                        f"t={x[0]}-{x[-1]} min"
                    ),
                    transform=ax.transAxes,
                    ha="right",
                    va="top",
                    fontsize=8.8,
                    bbox={
                        "boxstyle": "round,pad=0.25",
                        "facecolor": "white",
                        "edgecolor": "#d7d7d7",
                        "alpha": 0.92,
                    },
                )
                if cluster_pos == n_clusters - 1:
                    ax.set_xlabel("Post-capsaicin time (min)")
                panel_idx += 1

        fig.suptitle(
            "Cluster-Specific Shapelets",
            fontsize=14,
            fontweight="bold",
            y=1.02,
        )
    except Exception as exc:
        fig, ax = plt.subplots(figsize=(9, 6))
        _no_data(ax, f"Shapelets unavailable: {exc}")
    _save(fig, output_path)


def generate_figure12(output_path: str) -> None:
    print("Generating Figure 12: symptom-region heatmap...")
    fig, ax = plt.subplots(figsize=(9, 7))
    matrix = _top_matrix("textmining_symptom_region_matrix.csv", n_rows=10, n_cols=9)
    if matrix is None:
        _no_data(ax, "Symptom-Region Co-occurrence")
    else:
        sns.heatmap(matrix, cmap=PALETTE_NAME, ax=ax, cbar_kws={"label": "Count"})
        ax.set_title("Symptom-Region Co-occurrence", fontweight="bold")
        ax.set_xlabel("Region")
        ax.set_ylabel("Symptom")
    _save(fig, output_path)


def generate_figure13(output_path: str) -> None:
    print("Generating Figure 13: symptom-Rome IV heatmap...")
    fig, ax = plt.subplots(figsize=(9, 7))
    matrix = _top_matrix("textmining_symptom_disease_matrix.csv", n_rows=10, n_cols=8)
    if matrix is None:
        _no_data(ax, "Symptom-Rome IV Co-occurrence")
    else:
        sns.heatmap(matrix, cmap=PALETTE_NAME, ax=ax, cbar_kws={"label": "Count"})
        ax.set_title("Symptom-Rome IV Co-occurrence", fontweight="bold")
        ax.set_xlabel("Rome IV category")
        ax.set_ylabel("Symptom")
    _save(fig, output_path)


def generate_figure14(output_path: str) -> None:
    print("Generating Figure 14: VAS direction classification...")
    fig, ax = plt.subplots(figsize=(9, 6))
    cls = _read_metric("prediction_classification_summary.csv")
    if cls is None or cls.empty:
        _no_data(ax, "VAS Direction Classification")
    else:
        cls_long = cls.melt(
            id_vars="model",
            value_vars=[c for c in ["accuracy", "balanced_accuracy", "f1_macro"] if c in cls.columns],
            var_name="metric",
            value_name="value",
        )
        sns.barplot(data=cls_long, x="model", y="value", hue="metric", palette=PALETTE_NAME, ax=ax)
        ax.set_title("VAS Direction Classification", fontweight="bold")
        ax.set_xlabel("")
        ax.set_ylabel("Score")
        ax.tick_params(axis="x", rotation=20)
    _save(fig, output_path)


def generate_figure15(output_path: str) -> None:
    print("Generating Figure 15: ECG/EGG feature importance...")
    fig, ax = plt.subplots(figsize=(8, 7))
    imp = _read_metric("ecg_egg_cluster_prediction_rf_importance.csv")
    if imp is None or imp.empty:
        _no_data(ax, "ECG/EGG Feature Importance")
    else:
        top = imp.sort_values("importance", ascending=False).head(12)
        sns.barplot(
            data=top,
            x="importance",
            y="feature",
            hue="feature",
            palette=PALETTE_NAME,
            legend=False,
            ax=ax,
        )
        ax.set_title("Random Forest Feature Importance", fontweight="bold")
        ax.set_xlabel("Importance")
        ax.set_ylabel("")
    _save(fig, output_path)


def generate_figure16(output_path: str) -> None:
    print("Generating Figure 16: ECG/EGG confusion matrix...")
    fig, ax = plt.subplots(figsize=(7, 6))
    cm = _read_metric("ecg_egg_cluster_prediction_cm.csv")
    metrics = _read_metric("ecg_egg_cluster_prediction_metrics.csv")
    if cm is None or cm.empty or metrics is None or metrics.empty:
        _no_data(ax, "ECG/EGG Confusion Matrix")
    else:
        best_model = metrics.sort_values("accuracy_mean", ascending=False).iloc[0]["model"]
        cm_best = cm[cm["model"] == best_model]
        matrix = (
            cm_best.pivot(index="true_cluster", columns="predicted_cluster", values="count")
            .reindex(index=[0, 1, 2], columns=[0, 1, 2])
            .fillna(0)
        )
        sns.heatmap(matrix, annot=True, fmt=".0f", cmap=PALETTE_NAME, cbar_kws={"label": "Count"}, ax=ax)
        ax.set_title(f"ECG/EGG Confusion Matrix: {best_model}", fontweight="bold")
        ax.set_xlabel("Predicted phenotype")
        ax.set_ylabel("True phenotype")
    _save(fig, output_path)


def make_figure_map(
    baseline_path: str | None = None,
    metrics_dir: str = METRICS_DIR,
) -> dict[str, tuple[str, Callable[[str], None]]]:
    """Return the manuscript figure registry for the requested data sources."""
    configure_sources(baseline_path=baseline_path, metrics_dir=metrics_dir)
    return {
        "1": ("figure1_group_mean_vas.png", generate_figure1),
        "2": ("figure2_phenotype_trajectories.png", generate_figure2),
        "3": ("figure3_symptom_burden.png", generate_figure3),
        "4": ("figure4_region_burden.png", generate_figure4),
        "5": ("figure5_early_window_classification.png", generate_figure5),
        "6": ("figure6_baseline_prediction_performance.png", generate_figure6),
        "7": ("figure7_age_by_phenotype.png", generate_figure7),
        "8": ("figure8_ecg_egg_features.png", generate_figure8),
        "9": ("figure9_onset_timing.png", generate_figure9),
        "10": ("figure10_survival_curves.png", generate_figure10),
        "11": ("figure11_shapelets.png", generate_figure11),
        "12": ("figure12_symptom_region_heatmap.png", generate_figure12),
        "13": ("figure13_symptom_rome_heatmap.png", generate_figure13),
        "14": ("figure14_direction_classification.png", generate_figure14),
        "15": ("figure15_ecg_feature_importance.png", generate_figure15),
        "16": ("figure16_ecg_confusion_matrix.png", generate_figure16),
    }


FIGURE_MAP = make_figure_map()


def main() -> None:
    set_publication_style()
    configure_sources()
    clean_figure_outputs(FIGURES_DIR)
    for filename, generator in FIGURE_MAP.values():
        generator(os.path.join(FIGURES_DIR, filename))
    print(f"\nManuscript figures saved to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
