#!/usr/bin/env python3
"""
Generate all manuscript figures using the magma palette and actual project data.
"""

import os
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec

from analysis.constants import (
    CLUSTER_COLORS,
    FIGURES_DIR,
    HEATMAP_CMAP,
    METRICS_DIR,
    SECONDARY_COLOR,
    TERTIARY_COLOR,
)
from analysis.data_loader import load_unified_baseline
from analysis.visualization.style import set_publication_style

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Palette: all colors derived from sns.color_palette("magma", ...)
# ---------------------------------------------------------------------------
_MAGMA_5 = sns.color_palette("magma", n_colors=5)
_MAGMA_8 = sns.color_palette("magma", n_colors=8)

PALETTE = {
    "primary": CLUSTER_COLORS[0],
    "secondary": CLUSTER_COLORS[1],
    "tertiary": CLUSTER_COLORS[2],
    "quaternary": _MAGMA_5[3],
    "cluster_0": CLUSTER_COLORS[0],
    "cluster_1": CLUSTER_COLORS[1],
    "cluster_2": CLUSTER_COLORS[2],
    "onset": _MAGMA_8[4],
    "relief": _MAGMA_8[5],
    "neutral": _MAGMA_8[6],
    "symptom": SECONDARY_COLOR,
    "region": TERTIARY_COLOR,
    "disease": _MAGMA_5[4],
}


def _magma(n: int) -> list:
    """Return n discrete magma colors as hex strings."""
    return [
        plt.matplotlib.colors.to_hex(c) for c in sns.color_palette("magma", n_colors=n)
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_dir(path: str) -> str:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    return path


def _load_baseline():
    df = load_unified_baseline()
    vas_cols = [c for c in df.columns if c.startswith("VAS_") and c.endswith("min")]
    # Sort by minute number
    vas_cols = sorted(
        vas_cols, key=lambda x: int(x.replace("VAS_", "").replace("min", ""))
    )
    return df, vas_cols


# ===========================================================================
# FIGURE 1: Temporal dynamics
# ===========================================================================
def generate_figure1(output_path: str) -> None:
    print("Generating Figure 1: Temporal dynamics...")
    df, vas_cols = _load_baseline()
    minutes = np.arange(1, len(vas_cols) + 1)

    fig = plt.figure(figsize=(16, 12))
    gs = GridSpec(2, 2, figure=fig, hspace=0.3, wspace=0.3)

    # --- Panel A: Group-level mean VAS trajectory ---
    ax1 = fig.add_subplot(gs[0, 0])
    mean_vas, sem_vas, sample_sizes = [], [], []
    for col in vas_cols:
        valid = pd.to_numeric(df[col], errors="coerce").dropna()
        mean_vas.append(valid.mean())
        sem_vas.append(valid.sem())
        sample_sizes.append(len(valid))
    mean_vas = np.array(mean_vas)
    sem_vas = np.array(sem_vas)

    ax1.plot(
        minutes, mean_vas, "-o", color=PALETTE["primary"], linewidth=2, markersize=5
    )
    ax1.fill_between(
        minutes,
        mean_vas - sem_vas,
        mean_vas + sem_vas,
        alpha=0.3,
        color=PALETTE["primary"],
    )
    ax1_twin = ax1.twinx()
    ax1_twin.bar(minutes, sample_sizes, alpha=0.3, color="gray", width=0.6)
    ax1_twin.set_ylabel("Sample Size", color="gray")
    ax1_twin.tick_params(axis="y", labelcolor="gray")
    ax1.set_xlabel("Time (minutes)")
    ax1.set_ylabel("Mean VAS Score")
    ax1.set_title("(A) Group-level Mean VAS Trajectory", fontweight="bold")
    ax1.set_xlim(0.5, len(vas_cols) + 0.5)

    auc = np.trapezoid(mean_vas, minutes)
    ax1.text(
        0.05,
        0.95,
        f"AUC = {auc:.2f}",
        transform=ax1.transAxes,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
    )

    # --- Panel B: Three methods side-by-side, PELT with double x-axis break ---
    inner_gs = GridSpecFromSubplotSpec(
        1,
        3,
        subplot_spec=gs[0, 1],
        wspace=0.22,
        width_ratios=[1.0, 2.75, 1.3],
    )
    ax2_t = fig.add_subplot(inner_gs[0, 0])
    ax2_d = fig.add_subplot(inner_gs[0, 1], sharey=ax2_t)

    cp_path = os.path.join(METRICS_DIR, "trajectory_change_points.csv")
    if os.path.exists(cp_path):
        cp_df = pd.read_csv(cp_path)
        n_total = len(cp_df)

        thresh = cp_df["pain_onset_min"].dropna()
        deriv = cp_df["pain_onset_derivative"].dropna()
        pelt = cp_df["change_point_rank"].dropna()
        half_n = n_total / 2

        # --- Threshold onset (left) ---
        bins_t = np.arange(0.5, 5.5, 1)
        ax2_t.hist(
            thresh.values,
            bins=bins_t,
            color=PALETTE["cluster_0"],
            edgecolor="black",
            alpha=0.8,
        )
        ax2_t.axhline(half_n, color="gray", linestyle="--", linewidth=1.5, alpha=0.6)
        ax2_t.set_xlim(0.5, 4.5)
        ax2_t.set_xticks([1, 2, 3, 4])
        ax2_t.tick_params(axis="x", labelsize=8)
        ax2_t.set_ylabel("Number of Participants")
        ax2_t.set_xlabel("Time (min)", fontsize=9)
        ax2_t.set_title(
            "Threshold onset\n(VAS > 3)", fontweight="bold", fontsize=9, loc="center"
        )

        # --- Derivative onset (middle, wider) ---
        bins_d = np.arange(1.5, 13.5, 1)
        ax2_d.hist(
            deriv.values,
            bins=bins_d,
            color=PALETTE["cluster_1"],
            edgecolor="black",
            alpha=0.8,
        )
        ax2_d.axhline(half_n, color="gray", linestyle="--", linewidth=1.5, alpha=0.6)
        ax2_d.set_xlim(1.5, 12.5)
        ax2_d.set_xticks(range(2, 13))
        ax2_d.tick_params(axis="x", labelsize=8)
        ax2_d.tick_params(axis="y", labelleft=False)
        ax2_d.set_xlabel("Time (min)", fontsize=9)
        ax2_d.set_title(
            "Derivative onset\n(\u0394VAS \u2265 0.5)",
            fontweight="bold",
            fontsize=9,
            loc="center",
        )

        # --- PELT change point (right, broken x-axis: 5 | 10 | 15) ---
        pelt_gs = GridSpecFromSubplotSpec(
            1,
            3,
            subplot_spec=inner_gs[0, 2],
            wspace=0.04,
            width_ratios=[1.7, 1.0, 1.0],
        )
        ax2_p1 = fig.add_subplot(pelt_gs[0, 0], sharey=ax2_t)
        ax2_p2 = fig.add_subplot(pelt_gs[0, 1], sharey=ax2_t)
        ax2_p3 = fig.add_subplot(pelt_gs[0, 2], sharey=ax2_t)

        # Segment 1: 5 min (bins 4.5–5.5)
        bins_p1 = np.arange(4.5, 6.5, 1)
        ax2_p1.hist(
            pelt.values,
            bins=bins_p1,
            color=PALETTE["cluster_2"],
            edgecolor="black",
            alpha=0.8,
        )
        ax2_p1.axhline(half_n, color="gray", linestyle="--", linewidth=1.5, alpha=0.6)
        ax2_p1.set_xlim(4.3, 6.7)
        ax2_p1.set_xticks([5])
        ax2_p1.tick_params(axis="x", labelsize=8)
        ax2_p1.tick_params(axis="y", labelleft=False)
        ax2_p1.spines["right"].set_visible(False)

        # Segment 2: 10 min (bins 9.5–10.5)
        bins_p2 = np.arange(9.5, 11.5, 1)
        ax2_p2.hist(
            pelt.values,
            bins=bins_p2,
            color=PALETTE["cluster_2"],
            edgecolor="black",
            alpha=0.8,
        )
        ax2_p2.axhline(half_n, color="gray", linestyle="--", linewidth=1.5, alpha=0.6)
        ax2_p2.set_xlim(9.3, 10.7)
        ax2_p2.set_xticks([10])
        ax2_p2.tick_params(axis="x", labelsize=8)
        ax2_p2.tick_params(axis="y", labelleft=False)
        ax2_p2.spines["left"].set_visible(False)
        ax2_p2.spines["right"].set_visible(False)

        # Segment 3: 15 min (bins 14.5–15.5)
        bins_p3 = np.arange(14.5, 16.5, 1)
        ax2_p3.hist(
            pelt.values,
            bins=bins_p3,
            color=PALETTE["cluster_2"],
            edgecolor="black",
            alpha=0.8,
        )
        ax2_p3.axhline(half_n, color="gray", linestyle="--", linewidth=1.5, alpha=0.6)
        ax2_p3.set_xlim(14.3, 15.7)
        ax2_p3.set_xticks([15])
        ax2_p3.tick_params(axis="x", labelsize=8)
        ax2_p3.tick_params(axis="y", labelleft=False)
        ax2_p3.spines["left"].set_visible(False)
        ax2_p3.set_xlabel("Time (min)", fontsize=9)

        # Break diagonals
        d = 0.02
        kwargs = dict(color="k", clip_on=False, linewidth=1.2)
        ax2_p1.plot((1 - d, 1 + d), (-d, +d), transform=ax2_p1.transAxes, **kwargs)
        ax2_p1.plot(
            (1 - d, 1 + d), (1 - d, 1 + d), transform=ax2_p1.transAxes, **kwargs
        )
        ax2_p2.plot((-d, +d), (-d, +d), transform=ax2_p2.transAxes, **kwargs)
        ax2_p2.plot((-d, +d), (1 - d, 1 + d), transform=ax2_p2.transAxes, **kwargs)
        ax2_p2.plot((1 - d, 1 + d), (-d, +d), transform=ax2_p2.transAxes, **kwargs)
        ax2_p2.plot(
            (1 - d, 1 + d), (1 - d, 1 + d), transform=ax2_p2.transAxes, **kwargs
        )
        ax2_p3.plot((-d, +d), (-d, +d), transform=ax2_p3.transAxes, **kwargs)
        ax2_p3.plot((-d, +d), (1 - d, 1 + d), transform=ax2_p3.transAxes, **kwargs)

        # Title on leftmost segment
        ax2_p1.set_title(
            "PELT change point", fontweight="bold", fontsize=9, loc="center", pad=12
        )

        ax2_t.set_ylim(0, 220)

        # Panel label (B)
        ax2_t.text(
            -0.22,
            1.05,
            "(B)",
            transform=ax2_t.transAxes,
            fontsize=13,
            fontweight="bold",
            va="top",
            ha="right",
        )
    else:
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.text(
            0.5,
            0.5,
            "Change point data not found",
            ha="center",
            va="center",
            transform=ax2.transAxes,
        )

    # --- Panel C: Kaplan-Meier survival curves (with CI from lifelines) ---
    ax3 = fig.add_subplot(gs[1, 0])
    from analysis.trajectory.survival import compute_km_curves

    try:
        # Prepare raw VAS array for survival module
        vas_raw = []
        for _, row in df.iterrows():
            vals = (
                pd.Series([row[c] for c in vas_cols])
                .apply(pd.to_numeric, errors="coerce")
                .dropna()
            )
            vas_raw.append(vals.values)
        max_len = max(len(v) for v in vas_raw)
        X_surv = np.full((len(vas_raw), max_len), np.nan)
        for i, v in enumerate(vas_raw):
            X_surv[i, : len(v)] = v

        km_result = compute_km_curves(X_surv, onset_thresh=3.0)
        kmf_onset = km_result["kmf_onset"]
        kmf_relief = km_result["kmf_relief"]

        # Plot onset with CI
        sf_onset = kmf_onset.survival_function_
        ci_onset = kmf_onset.confidence_interval_
        ax3.step(
            sf_onset.index,
            sf_onset.values,
            where="post",
            linewidth=2.5,
            color=PALETTE["onset"],
            label="Pain Onset (VAS > 3)",
        )
        ax3.fill_between(
            ci_onset.index,
            ci_onset.iloc[:, 0].values,
            ci_onset.iloc[:, 1].values,
            step="post",
            alpha=0.2,
            color=PALETTE["onset"],
        )

        # Plot relief with CI
        sf_relief = kmf_relief.survival_function_
        ci_relief = kmf_relief.confidence_interval_
        ax3.step(
            sf_relief.index,
            sf_relief.values,
            where="post",
            linewidth=2.5,
            color=PALETTE["relief"],
            label="Pain Relief (VAS < 1)",
        )
        ax3.fill_between(
            ci_relief.index,
            ci_relief.iloc[:, 0].values,
            ci_relief.iloc[:, 1].values,
            step="post",
            alpha=0.2,
            color=PALETTE["relief"],
        )

        ax3.axhline(0.5, color="gray", linestyle=":", alpha=0.5)

        med_onset = kmf_onset.median_survival_time_
        med_relief = kmf_relief.median_survival_time_
        if np.isfinite(med_onset) and np.isfinite(med_relief):
            ax3.text(
                0.5,
                0.5,
                (
                    f"Median onset: {med_onset:.1f} min\n"
                    f"Median relief: {med_relief:.1f} min"
                ),
                transform=ax3.transAxes,
                fontsize=10,
                verticalalignment="bottom",
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
            )
    except Exception as e:
        ax3.text(
            0.5,
            0.5,
            f"Survival analysis failed:\n{str(e)}",
            ha="center",
            va="center",
            transform=ax3.transAxes,
            fontsize=10,
        )
    ax3.set_xlabel("Time (minutes)")
    ax3.set_ylabel("Survival Probability")
    ax3.set_title("(C) Kaplan-Meier Survival Curves", fontweight="bold")
    ax3.legend(loc="upper right")
    ax3.set_ylim(0, 1.05)

    # --- Panel D: AUC distribution ---
    ax4 = fig.add_subplot(gs[1, 1])
    auc_values = []
    for _, row in df.iterrows():
        vals = (
            pd.Series([row[c] for c in vas_cols])
            .apply(pd.to_numeric, errors="coerce")
            .dropna()
        )
        if len(vals) >= 2:
            auc_values.append(np.trapezoid(vals.values, np.arange(1, len(vals) + 1)))
    if auc_values:
        ax4.hist(
            auc_values, bins=30, color=PALETTE["tertiary"], edgecolor="black", alpha=0.7
        )
        ax4.axvline(
            np.mean(auc_values),
            color="red",
            linestyle="--",
            linewidth=2,
            label=f"Mean: {np.mean(auc_values):.1f}",
        )
        ax4.axvline(
            np.median(auc_values),
            color="blue",
            linestyle="--",
            linewidth=2,
            label=f"Median: {np.median(auc_values):.1f}",
        )
        ax4.legend()
    ax4.set_xlabel("Area Under Curve (VAS·minutes)")
    ax4.set_ylabel("Number of Participants")
    ax4.set_title("(D) Distribution of Pain Exposure (AUC)", fontweight="bold")

    plt.suptitle(
        "Figure 1. Temporal Dynamics of Capsaicin-Induced Pain",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )
    _ensure_dir(output_path)
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: {output_path}")


# ===========================================================================
# FIGURE 2: DTW-based Clustering
# ===========================================================================
def generate_figure2(output_path: str) -> None:
    print("Generating Figure 2: DTW-based clustering...")
    df, vas_cols = _load_baseline()

    from analysis.trajectory.clustering import (
        compute_dtw_silhouette,
        dtw_kmeans_cluster,
        fuzzy_c_medoids,
        prepare_vas_data,
    )

    X, X_raw, scaler = prepare_vas_data(df, vas_cols)
    cluster_labels, centroids, _ = dtw_kmeans_cluster(X, n_clusters=3)
    sil_avg, sil_values = compute_dtw_silhouette(X, cluster_labels)

    # Fuzzy clustering
    labels_fuzzy, memberships, medoid_indices, fuzzy_history = fuzzy_c_medoids(
        X, n_clusters=3, return_history=True
    )

    fig = plt.figure(figsize=(18, 14))
    gs = GridSpec(3, 2, figure=fig, hspace=0.35, wspace=0.3)
    minutes = np.arange(1, len(vas_cols) + 1)

    # --- Panel A: DTW-KMeans centroids ---
    ax1 = fig.add_subplot(gs[0, 0])
    centroids_2d = centroids.squeeze()
    for k in range(3):
        n_k = np.sum(cluster_labels == k)
        ax1.plot(
            minutes,
            centroids_2d[k],
            "-o",
            color=PALETTE[f"cluster_{k}"],
            linewidth=3,
            markersize=5,
            label=f"Cluster {k + 1} (n={n_k})",
        )
    ax1.set_xlabel("Time (minutes)")
    ax1.set_ylabel("Normalized Pain Intensity")
    ax1.set_title("(A) Cluster Centroids (DBA)", fontweight="bold")
    ax1.legend(loc="upper right")

    # --- Panel B: Silhouette ---
    ax2 = fig.add_subplot(gs[0, 1])
    y_lower = 10
    for k in range(3):
        kth_vals = sil_values[cluster_labels == k]
        kth_vals.sort()
        size_k = len(kth_vals)
        y_upper = y_lower + size_k
        ax2.fill_betweenx(
            np.arange(y_lower, y_upper),
            0,
            kth_vals,
            alpha=0.7,
            color=PALETTE[f"cluster_{k}"],
            label=f"Cluster {k}",
        )
        ax2.text(-0.05, y_lower + 0.5 * size_k, str(k))
        y_lower = y_upper + 10
    ax2.axvline(
        x=sil_avg,
        linestyle="--",
        linewidth=2,
        color="red",
        label=f"Average = {sil_avg:.3f}",
    )
    ax2.set_xlabel("Silhouette Coefficient")
    ax2.set_ylabel("Cluster")
    ax2.set_title("(B) Silhouette Analysis (K=3)", fontweight="bold")
    ax2.set_yticks([])
    ax2.legend(loc="upper right")

    # --- Panel C: K selection ---
    ax3 = fig.add_subplot(gs[1, 0])
    k_values = np.arange(2, 7)
    sil_scores = []
    for k in k_values:
        try:
            labels_k, _, _ = dtw_kmeans_cluster(X, n_clusters=k)
            s, _ = compute_dtw_silhouette(X, labels_k)
            sil_scores.append(s)
        except Exception:
            sil_scores.append(np.nan)
    ax3.plot(
        k_values,
        sil_scores,
        "o-",
        linewidth=2.5,
        markersize=10,
        color=PALETTE["primary"],
    )
    ax3.axvline(3, color="red", linestyle="--", linewidth=2, label="Optimal K=3")
    ax3.set_xlabel("Number of Clusters (K)")
    ax3.set_ylabel("Average Silhouette Score")
    ax3.set_title("(C) Silhouette Analysis for K Selection", fontweight="bold")
    ax3.set_xticks(k_values)
    ax3.legend()

    # --- Panel D: Fuzzy c-medoids (actual medoid trajectories) ---
    ax4 = fig.add_subplot(gs[1, 1])
    for k in range(3):
        medoid_idx = medoid_indices[k]
        medoid_curve = X_raw[medoid_idx]
        n_k = np.sum(labels_fuzzy == k)
        ax4.plot(
            minutes,
            medoid_curve,
            "-o",
            color=PALETTE[f"cluster_{k}"],
            linewidth=3,
            markersize=5,
            label=f"Cluster {k + 1} (n={n_k})",
        )
    ax4.set_xlabel("Time (minutes)")
    ax4.set_ylabel("VAS Score")
    ax4.set_title("(D) Fuzzy C-Medoids (Actual Medoid Trajectories)", fontweight="bold")
    ax4.legend(loc="upper right")

    # --- Panel E: Fuzzy membership ---
    ax5 = fig.add_subplot(gs[2, 0])
    max_memberships = np.max(memberships, axis=1)
    ax5.hist(
        max_memberships,
        bins=25,
        color=PALETTE["quaternary"],
        edgecolor="black",
        alpha=0.7,
    )
    ax5.axvline(
        np.mean(max_memberships),
        color="red",
        linestyle="--",
        linewidth=2,
        label=f"Mean: {np.mean(max_memberships):.2f}",
    )
    ax5.set_xlabel("Maximum Fuzzy Membership")
    ax5.set_ylabel("Number of Participants")
    ax5.set_title("(E) Distribution of Fuzzy Cluster Memberships", fontweight="bold")
    ax5.legend()

    # --- Panel F: Fuzzy C-Medoids Convergence ---
    ax6 = fig.add_subplot(gs[2, 1])
    iterations = np.arange(1, len(fuzzy_history) + 1)
    ax6.plot(
        iterations,
        fuzzy_history,
        "o-",
        color=PALETTE["primary"],
        linewidth=2,
        markersize=4,
    )
    ax6.set_xlabel("Iteration")
    ax6.set_ylabel("Objective Function")
    ax6.set_title("(F) Fuzzy C-Medoids Convergence", fontweight="bold")
    ax6.grid(alpha=0.25)

    plt.suptitle(
        "Figure 2. DTW-based Clustering of Pain Trajectories",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )
    _ensure_dir(output_path)
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: {output_path}")


# ===========================================================================
# FIGURE 3: Shapelets
# ===========================================================================
def generate_figure3(output_path: str) -> None:
    print("Generating Figure 3: Shapelets...")
    df, vas_cols = _load_baseline()

    from analysis.trajectory.clustering import dtw_kmeans_cluster, prepare_vas_data
    from analysis.trajectory.shapelets import extract_shapelets

    X, X_raw, scaler = prepare_vas_data(df, vas_cols)
    labels, _, _ = dtw_kmeans_cluster(X, n_clusters=3)

    # Extract shapelets (fixed length 5, top 3 per cluster)
    shapelet_df = extract_shapelets(
        X_raw, labels, n_clusters=3, min_len=5, max_len=5, top_k=3
    )

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    cluster_names = ["Delayed-peak", "Early-sustained", "Late-rising"]

    for k in range(3):
        ax = axes[k]
        cluster_shapelets = shapelet_df[shapelet_df["target_cluster"] == k + 1]
        for _, s in cluster_shapelets.iterrows():
            length = int(s["length"])
            vals = [s[f"shapelet_pt{j}"] for j in range(1, length + 1)]
            x = np.arange(length)
            ax.plot(x, vals, color=PALETTE[f"cluster_{k}"], linewidth=2.5)
        ax.set_xlabel("Local time")
        ax.set_ylabel("Normalized signal")
        ax.set_title(
            f"({chr(65 + k)}) {cluster_names[k]} Responders", fontweight="bold"
        )
        ax.grid(alpha=0.25)

    plt.suptitle(
        "Figure 3. Cluster-specific Shapelets Derived from DTW-based Clustering",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )
    plt.tight_layout()
    _ensure_dir(output_path)
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: {output_path}")


# ===========================================================================
# FIGURE 4: Symptom Distribution
# ===========================================================================
def generate_figure4(output_path: str) -> None:
    print("Generating Figure 4: Symptom distribution...")
    fig = plt.figure(figsize=(16, 12))
    gs = GridSpec(2, 2, figure=fig, hspace=0.3, wspace=0.3)

    # Load tripartite edges for co-occurrence
    edges_path = os.path.join(METRICS_DIR, "textmining_tripartite_edges.csv")
    nodes_path = os.path.join(METRICS_DIR, "textmining_tripartite_nodes.csv")

    if os.path.exists(edges_path) and os.path.exists(nodes_path):
        edges = pd.read_csv(edges_path)
        nodes = pd.read_csv(nodes_path)

        symptom_nodes = nodes[nodes["node_type"] == "symptom"]["name"].tolist()
        region_nodes = nodes[nodes["node_type"] == "region"]["name"].tolist()

        # Build co-occurrence matrix
        cooc = np.zeros((len(symptom_nodes), len(region_nodes)))
        for _, e in edges.iterrows():
            if e["edge_type"] == "symptom_region":
                s_idx = (
                    symptom_nodes.index(e["source"])
                    if e["source"] in symptom_nodes
                    else None
                )
                r_idx = (
                    region_nodes.index(e["target"])
                    if e["target"] in region_nodes
                    else None
                )
                if s_idx is None:
                    s_idx = (
                        symptom_nodes.index(e["target"])
                        if e["target"] in symptom_nodes
                        else None
                    )
                    r_idx = (
                        region_nodes.index(e["source"])
                        if e["source"] in region_nodes
                        else None
                    )
                if s_idx is not None and r_idx is not None:
                    cooc[s_idx, r_idx] += e["weight"]

        # Panel A: Heatmap
        ax1 = fig.add_subplot(gs[0, :])
        sns.heatmap(
            cooc,
            annot=True,
            fmt=".0f",
            cmap=HEATMAP_CMAP,
            xticklabels=region_nodes,
            yticklabels=symptom_nodes,
            ax=ax1,
            cbar_kws={"label": "Co-occurrence Count"},
        )
        ax1.set_title("(A) Symptom-Region Co-occurrence Heatmap", fontweight="bold")
        ax1.set_xlabel("Anatomical Region")
        ax1.set_ylabel("Symptom")

        # Panel B: Symptom frequency
        ax2 = fig.add_subplot(gs[1, 0])
        symptom_counts = cooc.sum(axis=1)
        sorted_idx = np.argsort(symptom_counts)[::-1]
        ax2.barh(
            range(len(symptom_nodes)),
            symptom_counts[sorted_idx],
            color=PALETTE["primary"],
        )
        ax2.set_yticks(range(len(symptom_nodes)))
        ax2.set_yticklabels([symptom_nodes[i] for i in sorted_idx], fontsize=10)
        ax2.set_xlabel("Frequency")
        ax2.set_title("(B) Symptom Frequency Distribution", fontweight="bold")
        ax2.invert_yaxis()

        # Panel C: Region frequency
        ax3 = fig.add_subplot(gs[1, 1])
        region_counts = cooc.sum(axis=0)
        sorted_idx = np.argsort(region_counts)[::-1]
        ax3.barh(
            range(len(region_nodes)),
            region_counts[sorted_idx],
            color=PALETTE["secondary"],
        )
        ax3.set_yticks(range(len(region_nodes)))
        ax3.set_yticklabels([region_nodes[i] for i in sorted_idx], fontsize=10)
        ax3.set_xlabel("Frequency")
        ax3.set_title("(C) Region Frequency Distribution", fontweight="bold")
        ax3.invert_yaxis()
    else:
        ax1 = fig.add_subplot(gs[0, :])
        ax1.text(
            0.5,
            0.5,
            "Network data not found",
            ha="center",
            va="center",
            transform=ax1.transAxes,
        )
        ax2 = fig.add_subplot(gs[1, 0])
        ax2.axis("off")
        ax3 = fig.add_subplot(gs[1, 1])
        ax3.axis("off")

    plt.suptitle(
        (
            "Figure 4. Frequency Distribution and Spatial Mapping of "
            "Capsaicin-Induced Symptoms"
        ),
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )
    _ensure_dir(output_path)
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: {output_path}")


# ===========================================================================
# FIGURE 5: Network Analysis
# ===========================================================================
def generate_figure5(output_path: str) -> None:
    print("Generating Figure 5: Network analysis...")
    fig = plt.figure(figsize=(20, 16))
    gs = GridSpec(3, 2, figure=fig, hspace=0.35, wspace=0.3)

    edges_path = os.path.join(METRICS_DIR, "textmining_tripartite_edges.csv")
    nodes_path = os.path.join(METRICS_DIR, "textmining_tripartite_nodes.csv")
    rome_path = os.path.join(METRICS_DIR, "textmining_rome_mapping.csv")

    if not os.path.exists(edges_path) or not os.path.exists(nodes_path):
        ax = fig.add_subplot(111)
        ax.text(
            0.5,
            0.5,
            "Network data not found",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close()
        return

    edges = pd.read_csv(edges_path)
    nodes = pd.read_csv(nodes_path)

    # Panel A: Tripartite co-occurrence network
    ax1 = fig.add_subplot(gs[0, :])
    try:
        import networkx as nx

        G = nx.Graph()
        for _, node in nodes.iterrows():
            G.add_node(node["name"], node_type=node["node_type"])
        for _, edge in edges.iterrows():
            G.add_edge(
                edge["source"],
                edge["target"],
                weight=edge["weight"],
                edge_type=edge["edge_type"],
            )

        pos = nx.spring_layout(G, k=2, iterations=50, seed=42)
        color_map = {
            "symptom": PALETTE["symptom"],
            "region": PALETTE["region"],
            "disease": PALETTE["disease"],
        }
        node_colors = [
            color_map.get(G.nodes[n].get("node_type", ""), "gray") for n in G.nodes()
        ]
        node_sizes = [G.nodes[n].get("count", 1) * 100 for n in G.nodes()]

        nx.draw_networkx_nodes(
            G, pos, node_color=node_colors, node_size=node_sizes, alpha=0.8, ax=ax1
        )
        # Draw edges with different styles per type
        for edge_type, style in [
            ("symptom_region", "solid"),
            ("symptom_disease", "dashed"),
            ("region_disease", "dotted"),
        ]:
            type_edges = [
                (u, v)
                for u, v, d in G.edges(data=True)
                if d.get("edge_type") == edge_type
            ]
            if type_edges:
                nx.draw_networkx_edges(
                    G, pos, edgelist=type_edges, alpha=0.3, style=style, ax=ax1
                )
        nx.draw_networkx_labels(G, pos, font_size=8, ax=ax1)
        ax1.set_title(
            "(A) Symptom-Region-Disease Tripartite Network", fontweight="bold"
        )
        ax1.axis("off")

        legend_elements = [
            mpatches.Patch(facecolor=PALETTE["symptom"], label="Symptoms"),
            mpatches.Patch(facecolor=PALETTE["region"], label="Regions"),
            mpatches.Patch(facecolor=PALETTE["disease"], label="Diseases"),
        ]
        ax1.legend(handles=legend_elements, loc="upper left")
    except ImportError:
        ax1.text(
            0.5,
            0.5,
            "NetworkX required",
            ha="center",
            va="center",
            transform=ax1.transAxes,
        )

    # Load matrices
    sr_path = os.path.join(METRICS_DIR, "textmining_symptom_region_matrix.csv")
    sd_path = os.path.join(METRICS_DIR, "textmining_symptom_disease_matrix.csv")
    rd_path = os.path.join(METRICS_DIR, "textmining_region_disease_matrix.csv")

    # Panel B: Symptom-Disease heatmap
    ax2 = fig.add_subplot(gs[1, 0])
    if os.path.exists(sd_path):
        sd = pd.read_csv(sd_path, index_col=0)
        sns.heatmap(sd, cmap=HEATMAP_CMAP, ax=ax2, cbar_kws={"label": "Score"})
        ax2.set_title("(B) Symptom-Disease Association Matrix", fontweight="bold")
        ax2.set_xticklabels(ax2.get_xticklabels(), rotation=45, ha="right", fontsize=9)
    else:
        ax2.text(
            0.5,
            0.5,
            "Data not found",
            ha="center",
            va="center",
            transform=ax2.transAxes,
        )

    # Panel C: Region-Disease heatmap
    ax3 = fig.add_subplot(gs[1, 1])
    if os.path.exists(rd_path):
        rd = pd.read_csv(rd_path, index_col=0)
        sns.heatmap(rd, cmap=HEATMAP_CMAP, ax=ax3, cbar_kws={"label": "Score"})
        ax3.set_title("(C) Region-Disease Mapping Heatmap", fontweight="bold")
        ax3.set_xticklabels(ax3.get_xticklabels(), rotation=45, ha="right", fontsize=9)
    else:
        ax3.text(
            0.5,
            0.5,
            "Data not found",
            ha="center",
            va="center",
            transform=ax3.transAxes,
        )

    # Panel D: Symptom-Region normalized heatmap
    ax4 = fig.add_subplot(gs[2, 0])
    if os.path.exists(sr_path):
        sr = pd.read_csv(sr_path, index_col=0)
        sr_norm = sr.div(sr.sum(axis=1), axis=0).fillna(0)
        sns.heatmap(
            sr_norm,
            annot=True,
            fmt=".2f",
            cmap=HEATMAP_CMAP,
            ax=ax4,
            cbar_kws={"label": "Proportion"},
        )
        ax4.set_title("(D) Row-normalized Symptom-Region Heatmap", fontweight="bold")
    else:
        ax4.text(
            0.5,
            0.5,
            "Data not found",
            ha="center",
            va="center",
            transform=ax4.transAxes,
        )

    # Panel E: Rome IV distribution
    ax5 = fig.add_subplot(gs[2, 1])
    if os.path.exists(rome_path):
        rome = pd.read_csv(rome_path)
        counts = rome["top_disease"].value_counts()
        counts = counts[counts.index != "No Match"]
        if len(counts) > 0:
            colors = _magma(len(counts))
            ax5.barh(range(len(counts)), counts.values, color=colors)
            ax5.set_yticks(range(len(counts)))
            ax5.set_yticklabels(counts.index, fontsize=10)
            ax5.set_xlabel("Number of Participants")
            ax5.set_title(
                "(E) Distribution of Rome IV-Aligned Categories", fontweight="bold"
            )
            ax5.invert_yaxis()
            total = counts.sum()
            for i, v in enumerate(counts.values):
                ax5.text(
                    v + 0.5, i, f"{v} ({v / total * 100:.1f}%)", va="center", fontsize=9
                )
    else:
        ax5.text(
            0.5,
            0.5,
            "Rome mapping data not found",
            ha="center",
            va="center",
            transform=ax5.transAxes,
        )

    plt.suptitle(
        "Figure 5. Network Analysis of Capsaicin-Induced Symptoms",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )
    _ensure_dir(output_path)
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: {output_path}")


# ===========================================================================
# FIGURE 6: Short-term Direction Prediction
# ===========================================================================
def generate_figure6(output_path: str) -> None:
    print("Generating Figure 6: Direction prediction...")
    fig = plt.figure(figsize=(16, 7))
    gs = GridSpec(1, 2, figure=fig, wspace=0.3)

    fold_path = os.path.join(METRICS_DIR, "prediction_classification_fold_metrics.csv")
    summary_path = os.path.join(METRICS_DIR, "prediction_classification_summary.csv")

    if os.path.exists(fold_path) and os.path.exists(summary_path):
        fold_df = pd.read_csv(fold_path)
        summary = pd.read_csv(summary_path)

        models = fold_df["model"].unique().tolist()

        # Panel A: Confusion matrices from actual evaluation
        ax1 = fig.add_subplot(gs[0, 0])
        inner_gs = GridSpecFromSubplotSpec(
            1, len(models), subplot_spec=gs[0, 0], wspace=0.4
        )

        # Load and aggregate confusion matrices per model
        cm_path = os.path.join(METRICS_DIR, "prediction_classification_cms.json")
        model_cms = {}
        if os.path.exists(cm_path):
            import json

            with open(cm_path) as f:
                cms = json.load(f)
            for key, mat in cms.items():
                model_name = key.split("_fold_")[0]
                if model_name not in model_cms:
                    model_cms[model_name] = np.array(mat)
                else:
                    model_cms[model_name] += np.array(mat)

        global_vmax = max((m.max() for m in model_cms.values()), default=1)

        for idx, model in enumerate(models):
            ax = fig.add_subplot(inner_gs[0, idx])
            cm = model_cms.get(model, np.array([[0, 0], [0, 0]]))
            sns.heatmap(
                cm,
                annot=True,
                fmt="d",
                cmap=HEATMAP_CMAP,
                ax=ax,
                xticklabels=["Non-decrease", "Decrease"],
                yticklabels=["Non-decrease", "Decrease"],
                cbar=False,
                vmin=0,
                vmax=global_vmax,
                square=True,
                linewidths=1,
            )
            ax.set_title(model, fontweight="bold", fontsize=11)
            ax.set_xlabel("Predicted", fontsize=10)
            if idx == 0:
                ax.set_ylabel("Actual", fontsize=10)

        fig.text(
            0.25,
            0.95,
            "(A) Confusion Matrices",
            ha="center",
            fontsize=13,
            fontweight="bold",
        )

        # Panel B: Performance bars from actual summary
        ax2 = fig.add_subplot(gs[0, 1])
        metrics = ["accuracy", "balanced_accuracy", "f1_macro", "f1_weighted"]
        metric_labels = ["Accuracy", "Balanced Acc", "Macro F1", "Weighted F1"]
        x = np.arange(len(models))
        width = 0.2
        colors = _magma(len(metrics))

        for i, (metric, label, color) in enumerate(zip(metrics, metric_labels, colors)):
            vals = [
                summary[summary["model"] == m][metric].values[0]
                if metric in summary.columns
                else 0
                for m in models
            ]
            ax2.bar(x + (i - 1.5) * width, vals, width, label=label, color=color)

        ax2.set_xlabel("Model")
        ax2.set_ylabel("Score")
        ax2.set_title("(B) Model Performance Comparison", fontweight="bold")
        ax2.set_xticks(x)
        ax2.set_xticklabels(models)
        ax2.legend(loc="lower right", fontsize=9)
        ax2.set_ylim(0, 1)
        ax2.axhline(0.5, color="gray", linestyle="--", alpha=0.5)
    else:
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.text(
            0.5,
            0.5,
            "Prediction data not found",
            ha="center",
            va="center",
            transform=ax1.transAxes,
        )
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.text(
            0.5,
            0.5,
            "Prediction data not found",
            ha="center",
            va="center",
            transform=ax2.transAxes,
        )

    plt.suptitle(
        "Figure 6. Short-term Direction Prediction of Symptom Dynamics",
        fontsize=15,
        fontweight="bold",
        y=1.02,
    )
    _ensure_dir(output_path)
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: {output_path}")


# ===========================================================================
# FIGURE 7: Cluster (Phenotype) Prediction from Baseline Features
# ===========================================================================
def generate_figure7(output_path: str) -> None:
    print("Generating Figure 7: Cluster prediction...")
    fig = plt.figure(figsize=(18, 7))
    gs = GridSpec(1, 3, figure=fig, wspace=0.38)

    metrics_dir = METRICS_DIR
    current_dir = os.path.join(metrics_dir, "current_exposure_adjusted")
    cluster_labels = ["Delayed-peak", "Early-sustained", "Late-rising"]
    current_metrics_path = os.path.join(
        current_dir, "current_cluster_prediction_metrics.csv"
    )
    current_cm_path = os.path.join(
        current_dir, "subject_classification_prefix_0min_cm.csv"
    )
    current_baseline_path = os.path.join(
        current_dir, "baseline_all_exposure_target_abs_0.5.csv"
    )
    use_current = os.path.exists(current_metrics_path) and os.path.exists(
        current_cm_path
    )
    best_model = None
    if use_current:
        current_metrics = pd.read_csv(current_metrics_path)
        best_model = current_metrics.iloc[0]["model"]

    # Panel A: Confusion matrix for selected current model when available.
    ax1 = fig.add_subplot(gs[0, 0])
    if use_current:
        cm_df = pd.read_csv(current_cm_path)
        model_cm = cm_df[cm_df["model"] == best_model]
        cm = np.zeros((3, 3), dtype=int)
        for _, row in model_cm.iterrows():
            cm[int(row["true_cluster"]), int(row["predicted_cluster"])] = int(
                row["count"]
            )

        ax1.imshow(cm, cmap="Blues", aspect="auto")
        ax1.set_xticks(range(3))
        ax1.set_yticks(range(3))
        ax1.set_xticklabels(cluster_labels, rotation=45, ha="right", fontsize=9)
        ax1.set_yticklabels(cluster_labels, fontsize=9)
        ax1.set_xlabel("Predicted", fontsize=10)
        ax1.set_ylabel("True", fontsize=10)
        ax1.set_title(f"(A) Confusion Matrix ({best_model})", fontweight="bold")
        for i in range(3):
            for j in range(3):
                color = "white" if cm[i, j] > cm.max() / 2 else "black"
                ax1.text(
                    j,
                    i,
                    str(cm[i, j]),
                    ha="center",
                    va="center",
                    color=color,
                    fontsize=11,
                    fontweight="bold",
                )
    else:
        ecg_cm_path = os.path.join(metrics_dir, "ecg_egg_cluster_prediction_cm.csv")
        if os.path.exists(ecg_cm_path):
            cm_df = pd.read_csv(ecg_cm_path)
            svm_cm = cm_df[cm_df["model"] == "SVM_RBF"]
            cm = np.zeros((3, 3), dtype=int)
            for _, row in svm_cm.iterrows():
                cm[int(row["true_cluster"]), int(row["predicted_cluster"])] = int(
                    row["count"]
                )

            ax1.imshow(cm, cmap="Blues", aspect="auto")
            ax1.set_xticks(range(3))
            ax1.set_yticks(range(3))
            ax1.set_xticklabels(cluster_labels, rotation=45, ha="right", fontsize=9)
            ax1.set_yticklabels(cluster_labels, fontsize=9)
            ax1.set_xlabel("Predicted", fontsize=10)
            ax1.set_ylabel("True", fontsize=10)
            ax1.set_title("(A) Confusion Matrix (SVM)", fontweight="bold")
            for i in range(3):
                for j in range(3):
                    color = "white" if cm[i, j] > cm.max() / 2 else "black"
                    ax1.text(
                        j,
                        i,
                        str(cm[i, j]),
                        ha="center",
                        va="center",
                        color=color,
                        fontsize=11,
                        fontweight="bold",
                    )
        else:
            ax1.text(
                0.5,
                0.5,
                "CM data not found",
                ha="center",
                va="center",
                transform=ax1.transAxes,
            )

    # Panel B: Performance comparison.
    ax2 = fig.add_subplot(gs[0, 1])
    ecg_summary_path = os.path.join(
        metrics_dir, "ecg_egg_cluster_prediction_metrics.csv"
    )

    if use_current:
        summary = current_metrics.copy()
        model_order = [
            "SparseLogistic",
            "SVM_Linear",
            "LogisticRegression",
            "HistGradientBoosting",
            "ExtraTrees",
            "RandomForest",
            "RidgeClassifier",
            "SVM_RBF",
            "KNN_Distance",
            "GaussianNB",
        ]
        title = "(B) Exposure-Adjusted Performance"
        ylim_top = 1.0
    elif os.path.exists(ecg_summary_path):
        summary = pd.read_csv(ecg_summary_path)
        model_order = [
            "LogisticRegression",
            "RandomForest",
            "SVM_RBF",
            "HistGradientBoosting",
            "MLP",
            "Stacking",
        ]
        title = "(B) Cross-validated Performance"
        ylim_top = 0.8
    else:
        summary = None

    if summary is not None:
        summary["model"] = pd.Categorical(
            summary["model"], categories=model_order, ordered=True
        )
        summary = summary.sort_values("model")

        models = summary["model"].tolist()
        x = np.arange(len(models))
        width = 0.25
        colors = _magma(3)

        metric_cols = ["balanced_accuracy_mean", "f1_macro_mean", "f1_weighted_mean"]
        metric_labels = ["Balanced Acc", "Macro F1", "Weighted F1"]

        for i, (col, label, color) in enumerate(
            zip(metric_cols, metric_labels, colors)
        ):
            vals = summary[col].values
            sds = summary[col.replace("_mean", "_sd")].values
            ax2.bar(
                x + (i - 1) * width,
                vals,
                width,
                label=label,
                color=color,
                yerr=sds,
                capsize=3,
            )

        ax2.set_xticks(x)
        ax2.set_xticklabels(models, fontsize=8, rotation=30, ha="right")
        ax2.set_ylabel("Score")
        ax2.set_title(title, fontweight="bold")
        ax2.legend(fontsize=8, loc="upper right")
        ax2.set_ylim(0, ylim_top)
        ax2.axhline(0.333, color="red", linestyle="--", alpha=0.6)
    else:
        ax2.text(
            0.5,
            0.5,
            "Metrics not found",
            ha="center",
            va="center",
            transform=ax2.transAxes,
        )

    # Panel C: Exposure associations for current analysis, else legacy coefficients.
    ax3 = fig.add_subplot(gs[0, 2])
    coef_path = os.path.join(metrics_dir, "cluster_prediction_feature_coef.csv")
    if use_current and os.path.exists(current_baseline_path):
        current_df = pd.read_csv(current_baseline_path)
        exposure_features = [
            "Spicy_food_frequency",
            "Usual_spiciness_level",
            "Spicy_food_preference",
            "Max_tolerable_spiciness",
            "CCEI",
            "Recent_spicy_intake_24h",
            "Time_since_last_intake_h",
            "Spicy_episodes_24h",
            "AES",
        ]
        corr_records = []
        for feature in exposure_features:
            if feature in current_df.columns:
                x = pd.to_numeric(current_df[feature], errors="coerce")
                y = pd.to_numeric(current_df["cluster"], errors="coerce")
                rho = x.corr(y, method="spearman")
                corr_records.append((feature, abs(rho)))
        corr_df = pd.DataFrame(corr_records, columns=["feature", "abs_spearman"])
        corr_df = corr_df.sort_values("abs_spearman", ascending=True)
        y_pos = np.arange(len(corr_df))
        ax3.barh(
            y_pos,
            corr_df["abs_spearman"].values,
            color=_magma(1)[0],
            edgecolor="gray",
            linewidth=0.5,
        )
        ax3.set_yticks(y_pos)
        ax3.set_yticklabels(corr_df["feature"].tolist(), fontsize=8)
        ax3.set_xlabel("|Spearman rho| vs cluster", fontsize=10)
        ax3.set_xlim(0, 0.6)
        ax3.set_title("(C) Adjusted Exposure Associations", fontweight="bold")
    elif os.path.exists(coef_path):
        coef_df = pd.read_csv(coef_path)
        feat_imp = (
            coef_df.groupby("feature")["abs_coefficient"]
            .mean()
            .sort_values(ascending=True)
        )
        top_n = 10
        top_feat = feat_imp.tail(top_n)
        y_pos = np.arange(len(top_feat))
        ax3.barh(
            y_pos, top_feat.values, color=_magma(1)[0], edgecolor="gray", linewidth=0.5
        )
        labels = []
        for name in top_feat.index:
            label = (
                name.replace("Sex_", "")
                .replace("Alcohol_consumption_", "")
                .replace("Recent_spicy_intake_24h_", "")
                .replace("Baseline_GI_symptoms_", "")
            )
            labels.append(label)
        ax3.set_yticks(y_pos)
        ax3.set_yticklabels(labels, fontsize=8)
        ax3.set_xlabel("Mean |Coefficient|", fontsize=10)
        ax3.set_title("(C) Top Predictive Features (LR)", fontweight="bold")
    else:
        ax3.text(
            0.5,
            0.5,
            "Coefficients not found",
            ha="center",
            va="center",
            transform=ax3.transAxes,
        )

    title = "Figure 7. Predicting Temporal Phenotypes from Exposure-Adjusted Features"
    if not use_current:
        title = "Figure 7. Predicting Temporal Phenotypes from Baseline Features"
    plt.suptitle(title, fontsize=15, fontweight="bold", y=0.98)
    _ensure_dir(output_path)
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: {output_path}")


# ===========================================================================
# Main
# ===========================================================================
def main():
    set_publication_style()
    print("=" * 60)
    print("Generating Manuscript Figures (magma palette)")
    print("=" * 60)

    os.makedirs(FIGURES_DIR, exist_ok=True)

    generate_figure1(os.path.join(FIGURES_DIR, "figure1_temporal_dynamics.png"))
    generate_figure2(os.path.join(FIGURES_DIR, "figure2_clustering.png"))
    generate_figure3(os.path.join(FIGURES_DIR, "figure3_shapelets.png"))
    generate_figure4(os.path.join(FIGURES_DIR, "figure4_symptom_distribution.png"))
    generate_figure5(os.path.join(FIGURES_DIR, "figure5_network_analysis.png"))
    generate_figure6(os.path.join(FIGURES_DIR, "figure6_prediction.png"))
    generate_figure7(os.path.join(FIGURES_DIR, "figure7_cluster_prediction.png"))

    print("\n" + "=" * 60)
    print("All manuscript figures generated successfully!")
    print(f"Output directory: {FIGURES_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
