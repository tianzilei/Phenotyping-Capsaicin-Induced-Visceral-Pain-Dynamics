#!/usr/bin/env python3
"""Generate main and supplementary manuscript figures with seaborn."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from analysis.constants import FIGURES_DIR, METRICS_DIR, REGION_CODE_MAP, SYMPTOM_CODE_MAP
from analysis.data_loader import get_vas_columns, load_unified_baseline
from analysis.parsing import map_codes, parse_compact_codes, parse_region_codes
from analysis.trajectory.clustering import dtw_kmeans_cluster, prepare_vas_data
from analysis.trajectory.shapelets import extract_shapelets
from analysis.visualization.style import set_publication_style

PALETTE_NAME = "magma"
PALETTE = sns.color_palette(PALETTE_NAME, n_colors=8)
CLUSTER_PALETTE = {0: PALETTE[1], 1: PALETTE[3], 2: PALETTE[5]}
CLUSTER_NAMES = {0: "Delayed-peak", 1: "Early-sustained", 2: "Late-rising"}
SUPPLEMENT_DIR = "supplement"


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
    """Remove old main and supplementary PNG outputs."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for png in out.glob("*.png"):
        png.unlink()
    supp = out / SUPPLEMENT_DIR
    supp.mkdir(parents=True, exist_ok=True)
    for png in supp.glob("*.png"):
        png.unlink()


def _time_from_vas_col(col: str) -> int:
    return int(col.replace("VAS_", "").replace("min", ""))


def _load_baseline() -> tuple[pd.DataFrame, list[str]]:
    df = load_unified_baseline()
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
    path = Path(METRICS_DIR) / name
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
    """Main Figure 1: core temporal dynamics."""
    print("Generating Figure 1: Main temporal phenotypes...")
    df, vas_cols = _load_baseline()
    long_df = _vas_long(df, vas_cols)
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    sns.lineplot(
        data=long_df,
        x="time_min",
        y="VAS",
        estimator="mean",
        errorbar="se",
        marker="o",
        color=PALETTE[2],
        ax=axes[0],
    )
    axes[0].set_title("(A) Group Mean VAS Trajectory", fontweight="bold")
    axes[0].set_xlabel("Time (min)")
    axes[0].set_ylabel("VAS")

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
            ax=axes[1],
        )
        _cluster_legend(axes[1], long_df["cluster"])
    else:
        _no_data(axes[1], "(B) Phenotype Trajectories")
    axes[1].set_title("(B) Phenotype Trajectories", fontweight="bold")
    axes[1].set_xlabel("Time (min)")
    axes[1].set_ylabel("VAS")

    fig.suptitle("Figure 1. Temporal Pain Phenotypes", fontweight="bold", y=1.02)
    _save(fig, output_path)


def generate_figure2(output_path: str) -> None:
    """Main Figure 2: core symptom and region burden."""
    print("Generating Figure 2: Main symptom burden...")
    df, _ = _load_baseline()
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    symptom = _code_summary(df, "Symptom_codes", parse_compact_codes, SYMPTOM_CODE_MAP)
    if symptom.empty:
        _no_data(axes[0], "(A) Symptom Burden")
    else:
        sns.barplot(
            data=symptom,
            x="percent",
            y="label",
            hue="label",
            palette=PALETTE_NAME,
            legend=False,
            ax=axes[0],
        )
        axes[0].set_title("(A) Symptom Burden", fontweight="bold")
        axes[0].set_xlabel("Participants (%)")
        axes[0].set_ylabel("")

    region = _code_summary(df, "Region_code", parse_region_codes, REGION_CODE_MAP)
    if region.empty:
        _no_data(axes[1], "(B) Pain Region Burden")
    else:
        sns.barplot(
            data=region,
            x="percent",
            y="label",
            hue="label",
            palette=PALETTE_NAME,
            legend=False,
            ax=axes[1],
        )
        axes[1].set_title("(B) Pain Region Burden", fontweight="bold")
        axes[1].set_xlabel("Participants (%)")
        axes[1].set_ylabel("")

    fig.suptitle("Figure 2. Symptom and Pain Region Burden", fontweight="bold", y=1.02)
    _save(fig, output_path)


def generate_figure3(output_path: str) -> None:
    """Main Figure 3: core phenotype prediction results."""
    print("Generating Figure 3: Main prediction performance...")
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    windows = _read_metric("subject_classification_window_comparison.csv")
    if windows is None or windows.empty:
        _no_data(axes[0], "(A) Early Window Phenotype Classification")
    else:
        sns.lineplot(
            data=windows,
            x="prefix_minutes",
            y="accuracy_mean",
            marker="o",
            color=PALETTE[4],
            ax=axes[0],
        )
        axes[0].fill_between(
            windows["prefix_minutes"],
            windows["accuracy_mean"] - windows["accuracy_sd"],
            windows["accuracy_mean"] + windows["accuracy_sd"],
            color=PALETTE[4],
            alpha=0.18,
        )
        axes[0].set_title("(A) Early VAS Window Comparison", fontweight="bold")
        axes[0].set_xlabel("Prefix window (min)")
        axes[0].set_ylabel("Accuracy")

    cluster_pred = _read_metric("cluster_prediction_metrics.csv")
    if cluster_pred is None or cluster_pred.empty:
        _no_data(axes[1], "(B) Phenotype Prediction")
    else:
        plot_df = cluster_pred.sort_values("accuracy_mean", ascending=False)
        sns.barplot(
            data=plot_df,
            x="accuracy_mean",
            y="model",
            hue="model",
            palette=PALETTE_NAME,
            legend=False,
            ax=axes[1],
        )
        axes[1].set_title("(B) Baseline/Physiology Phenotype Prediction", fontweight="bold")
        axes[1].set_xlabel("Accuracy")
        axes[1].set_ylabel("")

    fig.suptitle("Figure 3. Phenotype Prediction Performance", fontweight="bold", y=1.02)
    _save(fig, output_path)


def generate_figure4(output_path: str) -> None:
    """Main Figure 4: core physiological phenotype signal."""
    print("Generating Figure 4: Main baseline and physiology...")
    df, _ = _load_baseline()
    df = df.copy()
    if "cluster" in df.columns:
        df["cluster"] = pd.to_numeric(df["cluster"], errors="coerce")
        df["phenotype"] = df["cluster"].map(CLUSTER_NAMES)
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    if "phenotype" in df.columns and "Age" in df.columns:
        sns.boxplot(
            data=df,
            x="phenotype",
            y="Age",
            hue="phenotype",
            palette=list(CLUSTER_PALETTE.values()),
            legend=False,
            ax=axes[0],
        )
        axes[0].set_title("(A) Age by Phenotype", fontweight="bold")
        axes[0].set_xlabel("")
        axes[0].set_ylabel("Age")
    else:
        _no_data(axes[0], "(A) Age by Phenotype")

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
            ax=axes[1],
        )
        axes[1].set_title("(B) Standardized ECG/EGG Features", fontweight="bold")
        axes[1].set_xlabel("")
        axes[1].set_ylabel("Z-score")
        axes[1].tick_params(axis="x", rotation=25)
    else:
        _no_data(axes[1], "(B) Standardized ECG/EGG Features")

    fig.suptitle("Figure 4. Baseline and Physiological Phenotype Signals", fontweight="bold", y=1.02)
    _save(fig, output_path)


def generate_supplement_onset(output_path: str) -> None:
    print("Generating Supplement: onset timing...")
    cp = _read_metric("trajectory_change_points.csv")
    fig, ax = plt.subplots(figsize=(8, 6))
    if cp is None or cp.empty:
        _no_data(ax, "Supplementary Figure. Onset and Change-Point Timing")
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
        ax.set_title("Supplementary Figure. Onset and Change-Point Timing", fontweight="bold")
        ax.set_xlabel("Time (min)")
        ax.set_ylabel("Participants")
    _save(fig, output_path)


def generate_supplement_survival(output_path: str) -> None:
    print("Generating Supplement: survival curves...")
    surv = _read_metric("trajectory_survival_data.csv")
    fig, ax = plt.subplots(figsize=(8, 6))
    if surv is None or surv.empty:
        _no_data(ax, "Supplementary Figure. Kaplan-Meier Event Curves")
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
        ax.set_title("Supplementary Figure. Kaplan-Meier Event Curves", fontweight="bold")
        ax.set_xlabel("Time (min)")
        ax.set_ylabel("Survival probability")
    _save(fig, output_path)


def generate_supplement_shapelets(output_path: str) -> None:
    print("Generating Supplement: shapelets...")
    df, vas_cols = _load_baseline()
    fig, ax = plt.subplots(figsize=(9, 6))
    try:
        X, X_raw, _ = prepare_vas_data(df, vas_cols)
        labels, _, _ = dtw_kmeans_cluster(X, n_clusters=3)
        shapelets = extract_shapelets(X_raw, labels, n_clusters=3, min_len=5, max_len=5, top_k=3)
        rows = []
        for _, row in shapelets.iterrows():
            target = int(row["target_cluster"]) - 1
            for j in range(1, int(row["length"]) + 1):
                rows.append(
                    {
                        "shapelet_id": f"{target}-{int(row['source_subject'])}-{int(row['start'])}",
                        "local_time": j,
                        "value": row[f"shapelet_pt{j}"],
                        "phenotype": CLUSTER_NAMES.get(target, f"Cluster {target}"),
                    }
                )
        sns.lineplot(
            data=pd.DataFrame(rows),
            x="local_time",
            y="value",
            hue="phenotype",
            units="shapelet_id",
            estimator=None,
            palette={CLUSTER_NAMES[k]: v for k, v in CLUSTER_PALETTE.items()},
            linewidth=2,
            ax=ax,
        )
        ax.set_title("Supplementary Figure. Cluster-Specific Shapelets", fontweight="bold")
        ax.set_xlabel("Local time")
        ax.set_ylabel("Normalized VAS")
    except Exception as exc:
        _no_data(ax, f"Supplementary Figure. Shapelets unavailable: {exc}")
    _save(fig, output_path)


def generate_supplement_symptom_region(output_path: str) -> None:
    print("Generating Supplement: symptom-region heatmap...")
    fig, ax = plt.subplots(figsize=(9, 7))
    matrix = _top_matrix("textmining_symptom_region_matrix.csv", n_rows=10, n_cols=9)
    if matrix is None:
        _no_data(ax, "Supplementary Figure. Symptom-Region Co-occurrence")
    else:
        sns.heatmap(matrix, cmap=PALETTE_NAME, ax=ax, cbar_kws={"label": "Count"})
        ax.set_title("Supplementary Figure. Symptom-Region Co-occurrence", fontweight="bold")
        ax.set_xlabel("Region")
        ax.set_ylabel("Symptom")
    _save(fig, output_path)


def generate_supplement_symptom_rome(output_path: str) -> None:
    print("Generating Supplement: symptom-Rome heatmap...")
    fig, ax = plt.subplots(figsize=(9, 7))
    matrix = _top_matrix("textmining_symptom_disease_matrix.csv", n_rows=10, n_cols=8)
    if matrix is None:
        _no_data(ax, "Supplementary Figure. Symptom-Rome IV Co-occurrence")
    else:
        sns.heatmap(matrix, cmap=PALETTE_NAME, ax=ax, cbar_kws={"label": "Count"})
        ax.set_title("Supplementary Figure. Symptom-Rome IV Co-occurrence", fontweight="bold")
        ax.set_xlabel("Rome IV category")
        ax.set_ylabel("Symptom")
    _save(fig, output_path)


def generate_supplement_direction_models(output_path: str) -> None:
    print("Generating Supplement: direction classification...")
    fig, ax = plt.subplots(figsize=(9, 6))
    cls = _read_metric("prediction_classification_summary.csv")
    if cls is None or cls.empty:
        _no_data(ax, "Supplementary Figure. VAS Direction Classification")
    else:
        cls_long = cls.melt(
            id_vars="model",
            value_vars=[c for c in ["accuracy", "balanced_accuracy", "f1_macro"] if c in cls.columns],
            var_name="metric",
            value_name="value",
        )
        sns.barplot(data=cls_long, x="model", y="value", hue="metric", palette=PALETTE_NAME, ax=ax)
        ax.set_title("Supplementary Figure. VAS Direction Classification", fontweight="bold")
        ax.set_xlabel("")
        ax.set_ylabel("Score")
        ax.tick_params(axis="x", rotation=20)
    _save(fig, output_path)


def generate_supplement_ecg_importance(output_path: str) -> None:
    print("Generating Supplement: ECG/EGG feature importance...")
    fig, ax = plt.subplots(figsize=(8, 7))
    imp = _read_metric("ecg_egg_cluster_prediction_rf_importance.csv")
    if imp is None or imp.empty:
        _no_data(ax, "Supplementary Figure. ECG/EGG Feature Importance")
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
        ax.set_title("Supplementary Figure. Random Forest Feature Importance", fontweight="bold")
        ax.set_xlabel("Importance")
        ax.set_ylabel("")
    _save(fig, output_path)


def generate_supplement_ecg_confusion(output_path: str) -> None:
    print("Generating Supplement: ECG/EGG confusion matrix...")
    fig, ax = plt.subplots(figsize=(7, 6))
    cm = _read_metric("ecg_egg_cluster_prediction_cm.csv")
    metrics = _read_metric("ecg_egg_cluster_prediction_metrics.csv")
    if cm is None or cm.empty or metrics is None or metrics.empty:
        _no_data(ax, "Supplementary Figure. ECG/EGG Confusion Matrix")
    else:
        best_model = metrics.sort_values("accuracy_mean", ascending=False).iloc[0]["model"]
        cm_best = cm[cm["model"] == best_model]
        matrix = (
            cm_best.pivot(index="true_cluster", columns="predicted_cluster", values="count")
            .reindex(index=[0, 1, 2], columns=[0, 1, 2])
            .fillna(0)
        )
        sns.heatmap(matrix, annot=True, fmt=".0f", cmap=PALETTE_NAME, cbar_kws={"label": "Count"}, ax=ax)
        ax.set_title(f"Supplementary Figure. ECG/EGG Confusion Matrix: {best_model}", fontweight="bold")
        ax.set_xlabel("Predicted phenotype")
        ax.set_ylabel("True phenotype")
    _save(fig, output_path)


FIGURE_MAP = {
    "1": ("figure1_temporal_phenotypes.png", generate_figure1),
    "2": ("figure2_symptom_burden.png", generate_figure2),
    "3": ("figure3_prediction_performance.png", generate_figure3),
    "4": ("figure4_baseline_physiology.png", generate_figure4),
}

SUPPLEMENT_FIGURE_MAP = {
    "s1": ("supplement_onset_timing.png", generate_supplement_onset),
    "s2": ("supplement_survival_curves.png", generate_supplement_survival),
    "s3": ("supplement_shapelets.png", generate_supplement_shapelets),
    "s4": ("supplement_symptom_region_heatmap.png", generate_supplement_symptom_region),
    "s5": ("supplement_symptom_rome_heatmap.png", generate_supplement_symptom_rome),
    "s6": ("supplement_direction_classification.png", generate_supplement_direction_models),
    "s7": ("supplement_ecg_feature_importance.png", generate_supplement_ecg_importance),
    "s8": ("supplement_ecg_confusion_matrix.png", generate_supplement_ecg_confusion),
}


def main() -> None:
    set_publication_style()
    clean_figure_outputs(FIGURES_DIR)
    for filename, generator in FIGURE_MAP.values():
        generator(os.path.join(FIGURES_DIR, filename))
    supplement_dir = os.path.join(FIGURES_DIR, SUPPLEMENT_DIR)
    for filename, generator in SUPPLEMENT_FIGURE_MAP.values():
        generator(os.path.join(supplement_dir, filename))
    print(f"\nMain figures saved to {FIGURES_DIR}")
    print(f"Supplementary figures saved to {supplement_dir}")


if __name__ == "__main__":
    main()
