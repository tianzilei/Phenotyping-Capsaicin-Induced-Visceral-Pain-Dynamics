#!/usr/bin/env python3
"""Generate standalone manuscript figures with seaborn."""

from __future__ import annotations

import os
import shutil
import textwrap
from pathlib import Path
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import PowerNorm
import numpy as np
import pandas as pd
import seaborn as sns

from analysis.constants import FIGURES_DIR, METRICS_DIR, REGION_CODE_MAP, SYMPTOM_CODE_MAP
from analysis.data_loader import get_vas_columns, load_analysis_ready_baseline
from analysis.parsing import map_codes, parse_compact_codes, parse_region_codes
from analysis.visualization.style import set_publication_style

PALETTE_NAME = "magma"
PALETTE = sns.color_palette(PALETTE_NAME, n_colors=8)
CLUSTER_PALETTE = {0: PALETTE[1], 1: PALETTE[3], 2: PALETTE[5]}
CLUSTER_NAMES = {0: "Delayed-peak", 1: "Early-sustained", 2: "Late-rising"}
CLUSTER_TICK_LABELS = {
    0: "Delayed\npeak",
    1: "Early\nsustained",
    2: "Late\nrising",
}
NOMINAL_BAR_COLOR = "#5f6470"
HIGHLIGHT_COLOR = "#b73779"
PERFORMANCE_COLOR = "#3f6c8a"
HEATMAP_CMAP = sns.color_palette("rocket_r", as_cmap=True)
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
    ax.set_title(title)
    ax.set_axis_off()


def _wrap_label(label: object, width: int = 16) -> str:
    return "\n".join(textwrap.wrap(str(label), width=width, break_long_words=False))


def _short_feature_label(feature: str) -> str:
    labels = {
        "mean_HR": "Mean HR",
        "SDNN": "SDNN",
        "LF_HF_ratio": "LF/HF\nratio",
        "dominant_freq_cpm": "Dominant\nfrequency",
        "pct_normogastria": "Normogastria\n%",
    }
    return labels.get(feature, feature.replace("_", " "))


def _short_model_label(model: object) -> str:
    label = str(model)
    replacements = {
        "LogisticRegression": "Logistic",
        "RandomForest": "Random forest",
        "HistGradientBoosting": "Hist. gradient\nboosting",
        "SVM_RBF": "SVM RBF",
    }
    return replacements.get(label, label.replace("_", " "))


def _short_rome_label(label: object) -> str:
    replacements = {
        "Functional Abdominal Bloating/Distension-like": "FABD-like",
        "Functional Constipation / Defecatory Disorder-like": "FC/DD-like",
        "Functional Dyspepsia - PDS-like": "FD-PDS-like",
        "Chronic Nausea Vomiting Syndrome": "CNVS",
        "Irritable Bowel Syndrome-like": "IBS-like",
        "Unspecified Functional GI Symptom Pattern": "Unspecified\nFGI",
        "Biliary Pain-like": "Biliary\npain-like",
        "Belching Disorder": "Belching\ndisorder",
    }
    return replacements.get(str(label), _wrap_label(label, width=12))


def _title(ax: plt.Axes, title: str) -> None:
    ax.set_title(title, fontweight="normal", pad=8)


def _annotate_hbars(ax: plt.Axes, fmt: str = "{:.1f}") -> None:
    x_min, x_max = ax.get_xlim()
    pad = (x_max - x_min) * 0.012
    for patch in ax.patches:
        width = patch.get_width()
        if not np.isfinite(width):
            continue
        ax.text(
            width + pad,
            patch.get_y() + patch.get_height() / 2,
            fmt.format(width),
            va="center",
            ha="left",
            fontsize=8,
            color="#333333",
        )
    ax.set_xlim(x_min, x_max + (x_max - x_min) * 0.12)


def _plot_ranked_hbar(
    ax: plt.Axes,
    data: pd.DataFrame,
    x: str,
    y: str,
    color: str = NOMINAL_BAR_COLOR,
    highlight_top: int = 1,
) -> None:
    colors = [color] * len(data)
    for i in range(min(highlight_top, len(colors))):
        colors[i] = HIGHLIGHT_COLOR
    positions = np.arange(len(data))
    ax.barh(positions, data[x], color=colors, height=0.72)
    ax.set_yticks(positions)
    ax.set_yticklabels(data[y])
    ax.invert_yaxis()
    _annotate_hbars(ax)


def _prepare_vas_arrays(df: pd.DataFrame, vas_cols: list[str]) -> tuple[np.ndarray, np.ndarray]:
    data = df[vas_cols].copy()
    for col in data.columns:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.interpolate(axis=1, limit_area="inside").ffill(axis=1).bfill(axis=1)
    X_raw = data.to_numpy(dtype=float)
    means = X_raw.mean(axis=1, keepdims=True)
    stds = X_raw.std(axis=1, keepdims=True) + 1e-8
    X = (X_raw - means) / stds
    return X, X_raw


def clean_figure_outputs(output_dir: str = FIGURES_DIR) -> None:
    """Remove old manuscript PNG outputs."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for png in out.glob("figure*.png"):
        try:
            png.unlink()
        except PermissionError:
            print(f"  Warning: could not remove locked file, will overwrite: {png}")
    supp = out / "supplement"
    if supp.exists():
        try:
            shutil.rmtree(supp)
        except PermissionError:
            print(f"  Warning: could not remove locked directory: {supp}")


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
    for collection in ax.collections:
        collection.set_alpha(0.12)
    _title(ax, "Group Mean VAS Trajectory")
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
            markersize=4,
            palette=CLUSTER_PALETTE,
            ax=ax,
        )
        for collection in ax.collections:
            collection.set_alpha(0.10)
        _cluster_legend(ax, long_df["cluster"])
    else:
        _no_data(ax, "Phenotype Trajectories")
    _title(ax, "Phenotype-Specific VAS Trajectories")
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
        _plot_ranked_hbar(ax, symptom, x="percent", y="label")
        _title(ax, "Symptom Burden")
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
        _plot_ranked_hbar(ax, region, x="percent", y="label")
        _title(ax, "Pain Region Burden")
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
            markersize=4,
            color=PALETTE[4],
            ax=ax,
        )
        ax.fill_between(
            windows["prefix_minutes"],
            windows["accuracy_mean"] - windows["accuracy_sd"],
            windows["accuracy_mean"] + windows["accuracy_sd"],
            color=PALETTE[4],
            alpha=0.10,
        )
        _title(ax, "Early VAS Window Classification")
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
        plot_df = plot_df.copy()
        plot_df["model_label"] = plot_df["model"].map(_short_model_label)
        _plot_ranked_hbar(
            ax,
            plot_df,
            x="accuracy_mean",
            y="model_label",
            color=PERFORMANCE_COLOR,
            highlight_top=1,
        )
        _title(ax, "Baseline/Physiology Phenotype Prediction")
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
            fliersize=2.5,
            legend=False,
            ax=ax,
        )
        sns.stripplot(
            data=df,
            x="phenotype",
            y="Age",
            color="#333333",
            alpha=0.28,
            jitter=0.18,
            size=2.4,
            ax=ax,
        )
        _title(ax, "Age by Phenotype")
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

    feature_groups = {
        "ECG": [c for c in ["mean_HR", "SDNN", "LF_HF_ratio"] if c in df.columns],
        "EGG": [c for c in ["dominant_freq_cpm", "pct_normogastria"] if c in df.columns],
    }
    phys_cols = [c for cols in feature_groups.values() for c in cols]
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
        phys["feature_label"] = phys["feature"].map(_short_feature_label)
        fig, axes = plt.subplots(1, 2, figsize=(10.5, 5.8), sharey=True)
        handles = labels = None
        for ax, (group, cols) in zip(axes, feature_groups.items()):
            group_df = phys[phys["feature"].isin(cols)].copy()
            if group_df.empty:
                _no_data(ax, group)
                continue
            order = [_short_feature_label(c) for c in cols]
            sns.boxplot(
                data=group_df,
                x="feature_label",
                y="z_value",
                hue="phenotype",
                order=order,
                palette=list(CLUSTER_PALETTE.values()),
                fliersize=1.8,
                linewidth=0.9,
                ax=ax,
            )
            ax.axhline(0, color="#9a9a9a", linewidth=0.8, linestyle="--", zorder=0)
            _title(ax, group)
            ax.set_xlabel("")
            ax.set_ylabel("Z-score" if group == "ECG" else "")
            ax.tick_params(axis="x", rotation=0)
            if handles is None:
                handles, labels = ax.get_legend_handles_labels()
            legend = ax.get_legend()
            if legend is not None:
                legend.remove()
        if handles:
            fig.legend(
                handles,
                labels,
                title="Phenotype",
                loc="upper center",
                ncol=3,
                bbox_to_anchor=(0.5, 1.02),
                frameon=False,
            )
        fig.suptitle("Standardized ECG/EGG Features", fontsize=12, fontweight="normal", y=1.09)
        fig.tight_layout()
    else:
        fig, ax = plt.subplots(figsize=(9, 6))
        _no_data(ax, "Standardized ECG/EGG Features")

    _save(fig, output_path)


def generate_figure9(output_path: str) -> None:
    print("Generating Figure 9: onset timing...")
    cp = _read_metric("trajectory_change_points.csv")
    if cp is None or cp.empty:
        fig, ax = plt.subplots(figsize=(8, 6))
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
        cp_long = cp_long.dropna(subset=["method", "time_min"])
        methods = ["VAS > 3", "Derivative", "PELT"]
        methods = [m for m in methods if m in set(cp_long["method"])]
        fig, axes = plt.subplots(
            len(methods),
            1,
            figsize=(8.2, 1.95 * len(methods) + 1.0),
            sharex=True,
            constrained_layout=True,
        )
        axes = np.atleast_1d(axes)
        colors = sns.color_palette(PALETTE_NAME, n_colors=max(3, len(methods)))
        for idx, (ax, method) in enumerate(zip(axes, methods)):
            method_df = cp_long[cp_long["method"] == method]
            sns.histplot(
                data=method_df,
                x="time_min",
                bins=range(0, 22),
                color=colors[idx],
                alpha=0.52,
                edgecolor="white",
                linewidth=0.7,
                ax=ax,
            )
            median = method_df["time_min"].median()
            ax.axvline(median, color="#333333", linewidth=1.0, linestyle="--")
            ax.text(
                0.99,
                0.78,
                f"Median {median:.1f} min",
                transform=ax.transAxes,
                ha="right",
                va="center",
                fontsize=8,
            )
            ax.set_ylabel(method)
            ax.grid(axis="y", alpha=0.22)
        axes[0].set_title("Onset and Change-Point Timing", fontweight="normal", pad=8)
        axes[-1].set_xlabel("Time (min)")
    _save(fig, output_path)


def generate_figure10(output_path: str) -> None:
    print("Generating Figure 10: Kaplan-Meier event curves...")
    surv = _read_metric("trajectory_survival_data.csv")
    fig, ax = plt.subplots(figsize=(8, 6))
    if surv is None or surv.empty:
        _no_data(ax, "Kaplan-Meier Event Curves")
    else:
        from lifelines import KaplanMeierFitter

        for label, time_col, observed_col in [
            ("Onset", "onset_time", "onset_observed"),
            ("Relief", "relief_time", "relief_observed"),
        ]:
            kmf = KaplanMeierFitter()
            kmf.fit(surv[time_col], event_observed=surv[observed_col], label=label)
            kmf.plot_survival_function(
                ax=ax,
                ci_show=True,
                show_censors=True,
                color=PALETTE[2] if label == "Onset" else PALETTE[5],
                linewidth=1.9,
                censor_styles={"ms": 4, "marker": "|"},
            )
        _title(ax, "Kaplan-Meier Event Curves")
        ax.set_xlabel("Time (min)")
        ax.set_ylabel("Survival probability")
    _save(fig, output_path)


def generate_figure11(output_path: str) -> None:
    print("Generating Figure 11: cluster-specific shapelets...")
    df, vas_cols = _load_baseline()
    try:
        cached_shapelets = _read_metric("trajectory_shapelets.csv")
        if cached_shapelets is not None and not cached_shapelets.empty:
            shapelets = cached_shapelets
            cluster_labels = pd.to_numeric(df.get("cluster"), errors="coerce")
            valid_mask = cluster_labels.notna()
            df = df.loc[valid_mask].reset_index(drop=True)
            _, X_raw = _prepare_vas_arrays(df, vas_cols)
        else:
            from analysis.trajectory.shapelets import extract_shapelets

            if "cluster" not in df.columns:
                raise ValueError("cluster labels are missing; run trajectory first")

            cluster_labels = pd.to_numeric(df["cluster"], errors="coerce")
            valid_mask = cluster_labels.notna()
            if not valid_mask.any():
                raise ValueError("cluster labels are empty; run trajectory first")

            df = df.loc[valid_mask].reset_index(drop=True)
            labels = cluster_labels.loc[valid_mask].astype(int).to_numpy()
            _, X_raw = _prepare_vas_arrays(df, vas_cols)
            n_clusters = len(np.unique(labels))
            shapelets = extract_shapelets(
                X_raw,
                labels,
                n_clusters=n_clusters,
                min_len=5,
                max_len=5,
                top_k=3,
            )
            metrics_path = Path(_METRICS_SOURCE_DIR) / "trajectory_shapelets.csv"
            metrics_path.parent.mkdir(parents=True, exist_ok=True)
            shapelets.to_csv(metrics_path, index=False)
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
                    linewidth=1.3,
                    linestyle="--",
                    alpha=0.20,
                    zorder=1,
                )
                ax.plot(x, y, color=color, linewidth=2.0, marker="o", markersize=3.4, zorder=3)
                ax.fill_between(x, 0, y, color=color, alpha=0.05)
                ax.axhline(0, color="#b9b9b9", linewidth=0.8, linestyle="--", zorder=0)
                ax.grid(alpha=0.14, linewidth=0.6)
                ax.set_xlim(0, total_time)
                ax.set_ylim(y_min, y_max)
                ax.set_xticks([0, 5, 10, 15, 20])
                if cluster_pos == 0:
                    ax.set_title(
                        f"Top shapelet {shapelet_pos + 1}",
                        fontsize=9,
                        pad=7,
                        fontweight="normal",
                    )
                ax.text(
                    0.02,
                    0.97,
                    f"({chr(65 + panel_idx)})",
                    transform=ax.transAxes,
                    ha="left",
                    va="top",
                    fontsize=8.5,
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
                        fontsize=8.8,
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
                    fontsize=7.6,
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
            fontsize=12,
            fontweight="normal",
            y=1.015,
        )
    except Exception as exc:
        fig, ax = plt.subplots(figsize=(9, 6))
        _no_data(ax, f"Shapelets unavailable: {exc}")
    _save(fig, output_path)


def generate_figure12(output_path: str) -> None:
    print("Generating Figure 12: symptom-region heatmap...")
    fig, ax = plt.subplots(figsize=(9.4, 7.2))
    matrix = _top_matrix("textmining_symptom_region_matrix.csv", n_rows=10, n_cols=9)
    if matrix is None:
        _no_data(ax, "Symptom-Region Co-occurrence")
    else:
        annot = matrix.where(matrix >= matrix.to_numpy().max() * 0.25, other=np.nan)
        sns.heatmap(
            matrix,
            cmap=HEATMAP_CMAP,
            norm=PowerNorm(gamma=0.65, vmin=0, vmax=float(matrix.to_numpy().max())),
            annot=annot,
            fmt=".0f",
            annot_kws={"fontsize": 7.5},
            linewidths=0.4,
            linecolor="white",
            ax=ax,
            cbar_kws={"label": "Count"},
        )
        _title(ax, "Symptom-Region Co-occurrence")
        ax.set_xlabel("Region")
        ax.set_ylabel("Symptom")
        ax.set_xticklabels([_wrap_label(t.get_text(), width=11) for t in ax.get_xticklabels()], rotation=0)
        ax.set_yticklabels([_wrap_label(t.get_text(), width=18) for t in ax.get_yticklabels()], rotation=0)
    _save(fig, output_path)


def generate_figure13(output_path: str) -> None:
    print("Generating Figure 13: symptom-Rome IV heatmap...")
    fig, ax = plt.subplots(figsize=(9.8, 7.4))
    matrix = _top_matrix("textmining_symptom_disease_matrix.csv", n_rows=10, n_cols=8)
    if matrix is None:
        _no_data(ax, "Symptom-Rome IV Co-occurrence")
    else:
        annot = matrix.where(matrix >= matrix.to_numpy().max() * 0.25, other=np.nan)
        sns.heatmap(
            matrix,
            cmap=HEATMAP_CMAP,
            norm=PowerNorm(gamma=0.65, vmin=0, vmax=float(matrix.to_numpy().max())),
            annot=annot,
            fmt=".0f",
            annot_kws={"fontsize": 7.5},
            linewidths=0.4,
            linecolor="white",
            ax=ax,
            cbar_kws={"label": "Count"},
        )
        _title(ax, "Symptom-Rome IV Co-occurrence")
        ax.set_xlabel("Rome IV category")
        ax.set_ylabel("Symptom")
        ax.set_xticklabels([_short_rome_label(t.get_text()) for t in ax.get_xticklabels()], rotation=0)
        ax.set_yticklabels([_wrap_label(t.get_text(), width=18) for t in ax.get_yticklabels()], rotation=0)
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
        cls_long["model_label"] = cls_long["model"].map(_short_model_label)
        sns.barplot(
            data=cls_long,
            x="model_label",
            y="value",
            hue="metric",
            palette=sns.color_palette("Set2", n_colors=3),
            ax=ax,
        )
        _title(ax, "VAS Direction Classification")
        ax.set_xlabel("")
        ax.set_ylabel("Score")
        ax.tick_params(axis="x", rotation=0)
        ax.legend(title="Metric", frameon=False)
    _save(fig, output_path)


def generate_figure15(output_path: str) -> None:
    print("Generating Figure 15: ECG/EGG feature importance...")
    fig, ax = plt.subplots(figsize=(8, 7))
    imp = _read_metric("ecg_egg_cluster_prediction_rf_importance.csv")
    if imp is None or imp.empty:
        _no_data(ax, "ECG/EGG Feature Importance")
    else:
        top = imp.sort_values("importance", ascending=False).head(12)
        top = top.copy()
        top["feature_label"] = top["feature"].map(lambda x: _wrap_label(str(x).replace("_", " "), width=24))
        _plot_ranked_hbar(
            ax,
            top,
            x="importance",
            y="feature_label",
            color=PERFORMANCE_COLOR,
            highlight_top=3,
        )
        _title(ax, "Random Forest Feature Importance")
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
        row_totals = matrix.sum(axis=1).replace(0, np.nan)
        pct = matrix.div(row_totals, axis=0) * 100
        annot = matrix.astype(int).astype(str) + "\n" + pct.round(1).astype(str) + "%"
        sns.heatmap(
            matrix,
            annot=annot,
            fmt="",
            cmap=HEATMAP_CMAP,
            cbar_kws={"label": "Count"},
            linewidths=0.5,
            linecolor="white",
            ax=ax,
        )
        _title(ax, "ECG/EGG Confusion Matrix")
        ax.text(
            0.5,
            1.02,
            _short_model_label(best_model),
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=9,
            color="#555555",
        )
        labels = [CLUSTER_TICK_LABELS[i] for i in matrix.index]
        ax.set_xticklabels(labels, rotation=0)
        ax.set_yticklabels(labels, rotation=0)
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
