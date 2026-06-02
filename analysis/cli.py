"""Unified command-line entry point for the manuscript analysis workflow."""

import argparse
import os

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.constants import (
    ECG_EGG_DATA_DIR,
    FIGURES_DIR,
    METRICS_DIR,
    SUBJECT_INFO_FILE,
)
from analysis.visualization.style import set_publication_style


def save_to_baseline(baseline_path: str, updates_df: pd.DataFrame, id_col: str = "ID"):
    """Save analysis results back to baseline file (always overwrites)."""
    baseline = pd.read_csv(baseline_path)
    new_cols = [c for c in updates_df.columns if c != id_col]

    # Ensure ID columns are the same type before merging
    baseline[id_col] = baseline[id_col].astype(str)
    updates_df = updates_df.copy()
    updates_df[id_col] = updates_df[id_col].astype(str)

    baseline = baseline.merge(updates_df, on=id_col, how="left", suffixes=("", "_new"))

    for col in new_cols:
        new_col = f"{col}_new"
        if new_col in baseline.columns:
            baseline[col] = baseline[new_col]
            baseline = baseline.drop(columns=[new_col])

    baseline.to_csv(baseline_path, index=False, encoding="utf-8-sig")


def main():
    """Main entry point for analysis CLI."""
    parser = argparse.ArgumentParser(
        prog="analysis",
        description="Oral capsaicin-induced pain trajectory analysis tools",
    )
    parser.add_argument(
        "--baseline",
        "-b",
        default=SUBJECT_INFO_FILE,
        help="Path to unified subject_baseline_info.csv",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Trajectory command
    traj_parser = subparsers.add_parser("trajectory", help="VAS trajectory analysis")
    traj_parser.add_argument(
        "--method",
        choices=["dtw-kmeans", "fuzzy-cmedoids", "all"],
        default="all",
        help="Clustering method",
    )
    traj_parser.add_argument(
        "--n-clusters", type=int, default=3, help="Number of clusters"
    )
    traj_parser.add_argument("--no-plot", action="store_true", help="Skip plotting")

    # Text mining command
    tm_parser = subparsers.add_parser(
        "textmining", help="Text mining and Rome IV mapping"
    )
    tm_parser.add_argument("--no-plot", action="store_true", help="Skip plotting")

    # Network fusion command
    nf_parser = subparsers.add_parser("fusion", help="Network fusion analysis")
    nf_parser.add_argument("--no-plot", action="store_true", help="Skip plotting")

    # Prediction command
    pred_parser = subparsers.add_parser("predict", help="VAS prediction")
    pred_parser.add_argument(
        "--task",
        choices=["regression", "classification", "both"],
        default="both",
        help="Prediction task",
    )
    pred_parser.add_argument(
        "--window", type=int, default=3, help="Sliding window size"
    )
    pred_parser.add_argument("--no-plot", action="store_true", help="Skip plotting")

    # ECG/EGG command
    ecg_parser = subparsers.add_parser("ecg-egg", help="ECG/EGG signal analysis")
    ecg_parser.add_argument(
        "--data-dir", default=ECG_EGG_DATA_DIR, help="Signal data directory"
    )
    ecg_parser.add_argument("--no-plot", action="store_true", help="Skip plotting")
    ecg_parser.add_argument(
        "--re-extract", action="store_true", help="Re-extract features from raw signals"
    )

    # Subject classification command
    subj_parser = subparsers.add_parser(
        "subject-classify",
        help="Classify temporal phenotype from baseline and early VAS features",
    )
    subj_parser.add_argument(
        "--prefix-minutes",
        type=int,
        default=8,
        help=(
            "Use the first N VAS minutes as early trajectory features "
            "(0 = baseline only)"
        ),
    )
    subj_parser.add_argument(
        "--compare-prefixes",
        action="store_true",
        help="Compare baseline-only, 3, 5, 8, and 20 minute VAS windows",
    )

    # Tables command
    tables_parser = subparsers.add_parser(
        "tables", help="Generate manuscript tables (Markdown)"
    )
    tables_parser.add_argument(
        "--output-dir", default=METRICS_DIR, help="Output directory for Markdown tables"
    )

    # Baseline report command
    subparsers.add_parser(
        "baseline-report",
        help="Generate a focused BaselineData.csv analysis report",
    )

    # Figures command
    figures_parser = subparsers.add_parser(
        "figures", help="Generate all manuscript figures"
    )
    figures_parser.add_argument(
        "--output-dir", default=FIGURES_DIR, help="Output directory for figures"
    )
    figures_parser.add_argument(
        "--figures",
        nargs="+",
        default=None,
        help="Specific figures to generate (e.g., 1 2 3). Default: all",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # Apply publication-quality plot style globally
    set_publication_style()

    # Dispatch to subcommand
    if args.command == "trajectory":
        _run_trajectory(args)
    elif args.command == "textmining":
        _run_textmining(args)
    elif args.command == "fusion":
        _run_fusion(args)
    elif args.command == "predict":
        _run_predict(args)
    elif args.command == "ecg-egg":
        _run_ecg_egg(args)
    elif args.command == "subject-classify":
        _run_subject_classify(args)
    elif args.command == "tables":
        _run_tables(args)
    elif args.command == "baseline-report":
        _run_baseline_report(args)
    elif args.command == "figures":
        _run_figures(args)


def _run_tables(args):
    """Generate all manuscript tables."""
    from analysis.tables.generator import generate_all_tables

    generate_all_tables(
        baseline_path=args.baseline,
        output_dir=args.output_dir,
    )
    print(f"All tables saved to {args.output_dir}")


def _run_baseline_report(args):
    """Generate the focused baseline data analysis report."""
    from analysis.baseline_data_report import generate_report

    outputs = generate_report(args.baseline)
    print("Baseline report saved:")
    for name, path in outputs.items():
        print(f"  {name}: {path}")


def _run_figures(args):
    """Generate all manuscript figures."""
    import os

    from analysis.constants import FIGURES_DIR
    from analysis.visualization.style import set_publication_style

    set_publication_style()

    target_figures = args.figures
    output_dir = args.output_dir if args.output_dir else FIGURES_DIR
    os.makedirs(output_dir, exist_ok=True)

    # Import the figure generation functions
    from analysis.figures.manuscript import (
        generate_figure1,
        generate_figure2,
        generate_figure3,
        generate_figure4,
        generate_figure5,
        generate_figure6,
        generate_figure7,
    )

    figure_map = {
        "1": ("figure1_temporal_dynamics.png", generate_figure1),
        "2": ("figure2_clustering.png", generate_figure2),
        "3": ("figure3_shapelets.png", generate_figure3),
        "4": ("figure4_symptom_distribution.png", generate_figure4),
        "5": ("figure5_network_analysis.png", generate_figure5),
        "6": ("figure6_prediction.png", generate_figure6),
        "7": ("figure7_cluster_prediction.png", generate_figure7),
    }

    if target_figures:
        for fig_num in target_figures:
            if fig_num not in figure_map:
                print(f"Unknown figure number: {fig_num}. Available: 1-7")
                continue
            filename, gen_fn = figure_map[fig_num]
            gen_fn(os.path.join(output_dir, filename))
    else:
        generate_figure1(os.path.join(output_dir, "figure1_temporal_dynamics.png"))
        generate_figure2(os.path.join(output_dir, "figure2_clustering.png"))
        generate_figure3(os.path.join(output_dir, "figure3_shapelets.png"))
        generate_figure4(os.path.join(output_dir, "figure4_symptom_distribution.png"))
        generate_figure5(os.path.join(output_dir, "figure5_network_analysis.png"))
        generate_figure6(os.path.join(output_dir, "figure6_prediction.png"))
        generate_figure7(os.path.join(output_dir, "figure7_cluster_prediction.png"))

    print(f"\nAll figures saved to {output_dir}")


def _run_trajectory(args):
    """Run trajectory analysis."""
    from analysis.data_loader import (
        get_vas_columns,
        load_unified_baseline,
    )
    from analysis.trajectory import change_point, clustering, plotting, survival

    baseline_df = load_unified_baseline(args.baseline)
    vas_cols = get_vas_columns(baseline_df)

    figures_dir = FIGURES_DIR
    os.makedirs(figures_dir, exist_ok=True)

    output_csv = os.path.join(METRICS_DIR, "trajectory_clustered.csv")

    vas_df = baseline_df[["ID"] + vas_cols].copy()
    time_cols = get_vas_columns(vas_df)

    final_labels = None
    if args.method in ("dtw-kmeans", "all"):
        print("Running DTW-KMeans clustering...")
        X, X_raw, scaler = clustering.prepare_vas_data(vas_df, time_cols)
        labels, centroids, model = clustering.dtw_kmeans_cluster(
            X, n_clusters=args.n_clusters
        )
        final_labels = labels

        baseline_df["cluster"] = labels
        baseline_df.to_csv(output_csv, index=False)

        sil_avg, sil_values = clustering.compute_dtw_silhouette(X, labels)
        print(f"Silhouette score: {sil_avg:.4f}")

        if not args.no_plot:
            plotting.plot_cluster_centroids(
                centroids,
                labels,
                save_path=os.path.join(figures_dir, "cluster_centroids.png"),
            )

    if args.method in ("fuzzy-cmedoids", "all"):
        print("Running Fuzzy C-Medoids clustering...")
        X, X_raw, scaler = clustering.prepare_vas_data(vas_df, time_cols)
        labels, memberships, medoid_indices = clustering.fuzzy_c_medoids(
            X, n_clusters=args.n_clusters
        )
        final_labels = labels

        baseline_df["cluster"] = labels
        baseline_df.to_csv(output_csv, index=False)

    if final_labels is not None:
        cluster_df = pd.DataFrame(
            {"ID": baseline_df["ID"].values, "cluster": final_labels}
        )
        save_to_baseline(args.baseline, cluster_df)
        print(f"Cluster labels saved to baseline: {args.baseline}")

    # Change point detection
    print("Running change point detection...")
    vas_wide = baseline_df.set_index("ID")[vas_cols].copy()
    vas_wide = vas_wide.apply(pd.to_numeric, errors="coerce")
    vas_wide.columns = [
        int(c.replace("VAS_", "").replace("min", "")) for c in vas_wide.columns
    ]
    vas_wide = vas_wide.sort_index(axis=1)
    onset_df = change_point.detect_all_onsets(
        vas_wide, threshold=3.0, delta_thresh=0.5, penalty=0.5
    )
    onset_df.to_csv(
        os.path.join(METRICS_DIR, "trajectory_change_points.csv"), index=False
    )
    print(f"Change points: {len(onset_df)} subjects")

    # Survival analysis
    print("Running survival analysis...")
    X, _, _ = clustering.prepare_vas_data(baseline_df, vas_cols)
    X_raw = X.squeeze() if X.ndim == 3 else X
    km_result = survival.compute_km_curves(X_raw, onset_thresh=3.0)
    survival_df = pd.DataFrame(
        {
            "ID": baseline_df["ID"],
            "onset_time": km_result["onset_time"],
            "onset_observed": km_result["onset_observed"],
            "relief_time": km_result["relief_time"],
            "relief_observed": km_result["relief_observed"],
        }
    )
    survival_df.to_csv(
        os.path.join(METRICS_DIR, "trajectory_survival_data.csv"), index=False
    )
    median_relief = km_result["kmf_relief"].median_survival_time_
    logrank_p = km_result["logrank_pvalue"]
    print(f"Survival: median relief={median_relief} min, p={logrank_p:.4f}")

    if not args.no_plot:
        # Plot KM curves
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        km_result["kmf_onset"].plot_survival_function(ax=axes[0], ci_show=True)
        axes[0].set_title("Pain Onset (VAS > 3.0)")
        km_result["kmf_relief"].plot_survival_function(ax=axes[1], ci_show=True)
        axes[1].set_title("Pain Relief (VAS < 1.0)")
        plt.tight_layout()
        plt.savefig(
            os.path.join(figures_dir, "survival_km_curves.png"),
            dpi=150,
            bbox_inches="tight",
        )
        plt.close()
        print("Survival KM curves saved")

    print(f"Results saved to {METRICS_DIR}")
    if not args.no_plot:
        print(f"Figures saved to {figures_dir}")


def _run_textmining(args):
    """Run text mining analysis."""
    from analysis.data_loader import load_unified_baseline
    from analysis.text_mining import mapper, network_builder, plotting

    baseline_df = load_unified_baseline(args.baseline)

    figures_dir = FIGURES_DIR
    os.makedirs(figures_dir, exist_ok=True)

    symptom_cols = ["Region_code", "Symptom_codes", "Additional_symptoms"]
    available_cols = [c for c in symptom_cols if c in baseline_df.columns]

    if not available_cols:
        print("No symptom columns found in baseline data.")
        return

    symptoms_df = baseline_df[["ID"] + available_cols].copy()
    symptoms_df = symptoms_df.rename(
        columns={
            "Region_code": "Region",
            "Symptom_codes": "Symptom",
        }
    )

    print("Building Rome IV mapping...")
    rome_df = mapper.build_participant_rome_mapping(symptoms_df, id_col="ID")
    rome_df.to_csv(
        os.path.join(METRICS_DIR, "textmining_rome_mapping.csv"), index=False
    )

    print("Building tripartite network...")
    edges_df, nodes_df = network_builder.build_tripartite_edges(rome_df)
    edges_df.to_csv(
        os.path.join(METRICS_DIR, "textmining_tripartite_edges.csv"), index=False
    )
    nodes_df.to_csv(
        os.path.join(METRICS_DIR, "textmining_tripartite_nodes.csv"), index=False
    )

    print("Building co-occurrence matrices...")
    matrices = network_builder.build_cooccurrence_matrices(edges_df)
    for name, matrix in matrices.items():
        matrix.to_csv(os.path.join(METRICS_DIR, f"textmining_{name}_matrix.csv"))

    if not args.no_plot:
        plotting.plot_cooccurrence_heatmaps(
            matrices,
            save_path=os.path.join(figures_dir, "cooccurrence_heatmaps.png"),
        )

    rome_results = pd.DataFrame(
        {
            "ID": rome_df["participant_id"],
            "top_rome_disease": rome_df["top_disease"],
            "rome_match_score": rome_df["top_score"],
        }
    )
    save_to_baseline(args.baseline, rome_results)
    print(f"Rome IV mapping saved to baseline: {args.baseline}")

    print(f"Results saved to {METRICS_DIR}")
    if not args.no_plot:
        print(f"Figures saved to {figures_dir}")


def _run_fusion(args):
    """Run network fusion analysis."""
    from analysis.data_loader import load_unified_baseline

    baseline_df = load_unified_baseline(args.baseline)

    symptom_cols = ["Region_code", "Symptom_codes"]
    available_cols = [c for c in symptom_cols if c in baseline_df.columns]

    if not available_cols:
        print("No symptom columns found in baseline data.")
        return

    cols_to_include = ["ID"] + available_cols
    if "cluster" in baseline_df.columns:
        cols_to_include.append("cluster")

    fusion_df = baseline_df[cols_to_include].copy()
    fusion_df = fusion_df.rename(
        columns={
            "Region_code": "Region",
            "Symptom_codes": "Symptom",
        }
    )

    from analysis.network_fusion.fusion import (
        compute_cluster_symptom_weights,
    )

    cluster_symptom_df, cluster_region_df = compute_cluster_symptom_weights(
        fusion_df, cluster_col="cluster", symptom_col="Symptom", region_col="Region"
    )

    cluster_symptom_df.to_csv(
        os.path.join(METRICS_DIR, "fusion_cluster_symptom_weights.csv"), index=False
    )
    cluster_region_df.to_csv(
        os.path.join(METRICS_DIR, "fusion_cluster_region_weights.csv"), index=False
    )

    print("Fusion analysis complete.")
    print(f"Results saved to {METRICS_DIR}")


def _run_predict(args):
    """Run prediction analysis."""
    from analysis.data_loader import get_vas_columns, load_unified_baseline
    from analysis.prediction import classification, common, plotting, regression

    baseline_df = load_unified_baseline(args.baseline)
    vas_cols = get_vas_columns(baseline_df)
    time_cols = vas_cols

    figures_dir = FIGURES_DIR
    os.makedirs(figures_dir, exist_ok=True)

    all_preds_list = []

    if args.task in ("regression", "both"):
        print("Building regression dataset...")
        data, y_col = common.build_sliding_window_features(
            baseline_df, time_cols, window=args.window, target_mode="delta"
        )

        print("Evaluating regression models...")
        fold_df, summary, preds = regression.evaluate_regression_models(data, y_col)
        fold_df.to_csv(
            os.path.join(METRICS_DIR, "prediction_regression_fold_metrics.csv"),
            index=False,
        )
        summary.to_csv(
            os.path.join(METRICS_DIR, "prediction_regression_summary.csv"), index=False
        )

        all_preds_list.append(preds)

        if not args.no_plot:
            plotting.plot_observed_vs_predicted(
                preds,
                save_path=os.path.join(figures_dir, "regression_scatter.png"),
            )

    if args.task in ("classification", "both"):
        print("Building classification dataset...")
        data, y_col = classification.build_direction_dataset(
            baseline_df, time_cols, window=args.window
        )

        print("Evaluating classification models...")
        fold_df, summary, preds, cms = classification.evaluate_classification_models(
            data, y_col
        )
        fold_df.to_csv(
            os.path.join(METRICS_DIR, "prediction_classification_fold_metrics.csv"),
            index=False,
        )
        summary.to_csv(
            os.path.join(METRICS_DIR, "prediction_classification_summary.csv"),
            index=False,
        )

        import json

        cms_path = os.path.join(METRICS_DIR, "prediction_classification_cms.json")
        with open(cms_path, "w") as f:
            json.dump({k: v.tolist() for k, v in cms.items()}, f)

        all_preds_list.append(preds)

    if all_preds_list:
        all_preds = pd.concat(all_preds_list, ignore_index=True)

        subject_preds = (
            all_preds.groupby("subject_id")
            .agg({"predicted": "mean", "target": "mean"})
            .reset_index()
        )
        subject_preds.columns = ["ID", "predicted_vas_delta", "target_vas_delta"]

        if "model" in all_preds.columns:
            model_preds = (
                all_preds.groupby("subject_id")["model"]
                .agg(lambda x: x.value_counts().index[0] if len(x) > 0 else "unknown")
                .reset_index()
            )
            model_preds.columns = ["ID", "prediction_model"]
            subject_preds = subject_preds.merge(model_preds, on="ID", how="left")

        if "predicted" in all_preds.columns:
            subject_preds["predicted_direction"] = subject_preds[
                "predicted_vas_delta"
            ].apply(lambda x: 1 if x > 0.1 else (-1 if x < -0.1 else 0))

        save_to_baseline(args.baseline, subject_preds)
        print(f"Prediction results saved to baseline: {args.baseline}")

    print(f"Results saved to {METRICS_DIR}")
    if not args.no_plot:
        print(f"Figures saved to {figures_dir}")


def _run_ecg_egg(args):
    """Run ECG/EGG analysis."""
    from analysis.data_loader import check_signal_files, load_unified_baseline
    from analysis.ecg_egg import classification, features

    baseline_df = load_unified_baseline(args.baseline)

    figures_dir = FIGURES_DIR
    os.makedirs(figures_dir, exist_ok=True)

    if args.re_extract:
        print("Re-extracting features from raw signals...")
        from analysis.data_loader import load_subject_metadata

        baseline_df = load_subject_metadata(args.baseline)
        baseline_df["file_stem"] = baseline_df["ACQ_CNP_files"].str.replace(
            ".acq", "", regex=False
        )
        meta = check_signal_files(baseline_df, args.data_dir)

        print(f"Processing {len(meta)} subjects with signal files...")
        features_df = features.build_feature_matrix(meta, args.data_dir)
        features_df = classification.add_clinical_features(features_df, meta)
        features_df.to_csv(
            os.path.join(METRICS_DIR, "ecg_egg_features_extracted.csv"), index=False
        )

        ecg_egg_feature_cols = [
            "mean_HR",
            "median_HR",
            "min_HR",
            "max_HR",
            "HR_sd",
            "HR_cv",
            "mean_RR",
            "median_RR",
            "min_RR",
            "max_RR",
            "SDNN",
            "RMSSD",
            "pNN50",
            "pNN20",
            "CVSD",
            "total_power",
            "LF_power",
            "HF_power",
            "LF_HF_ratio",
            "log_LF",
            "log_HF",
            "log_total_power",
            "LFnu",
            "HFnu",
            "SD1",
            "SD2",
            "SD1_SD2_ratio",
            "ECG_SQI",
            "ECG_artifact_ratio",
            "ECG_RR_edit_ratio",
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
            "hr_egg_correlation",
            "ecg_egg_cross_corr_max",
            "ecg_egg_lag",
            "ecg_egg_coherence_mean",
            "ecg_egg_energy_ratio",
        ]
        available_feature_cols = [
            c for c in ecg_egg_feature_cols if c in features_df.columns
        ]
        features_to_save = features_df[["ID"] + available_feature_cols].copy()

        save_to_baseline(args.baseline, features_to_save)
        print(f"ECG/EGG features saved to baseline: {args.baseline}")

        print(f"Features extracted and saved to {METRICS_DIR}")
    else:
        ecg_egg_cols = [
            "ID",
            "Sex",
            "Age",
            "BMI",
            "Height_cm",
            "Weight_kg",
            "cluster",
            "mean_HR",
            "median_HR",
            "min_HR",
            "max_HR",
            "HR_sd",
            "HR_cv",
            "mean_RR",
            "median_RR",
            "min_RR",
            "max_RR",
            "SDNN",
            "RMSSD",
            "pNN50",
            "pNN20",
            "CVSD",
            "total_power",
            "LF_power",
            "HF_power",
            "LF_HF_ratio",
            "log_LF",
            "log_HF",
            "log_total_power",
            "LFnu",
            "HFnu",
            "SD1",
            "SD2",
            "SD1_SD2_ratio",
            "ECG_SQI",
            "ECG_artifact_ratio",
            "ECG_RR_edit_ratio",
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
            "hr_egg_correlation",
            "ecg_egg_cross_corr_max",
            "ecg_egg_lag",
            "ecg_egg_coherence_mean",
            "ecg_egg_energy_ratio",
        ]
        available_cols = [c for c in ecg_egg_cols if c in baseline_df.columns]
        features_df = baseline_df[available_cols].copy()
        features_df.to_csv(
            os.path.join(METRICS_DIR, "ecg_egg_features.csv"), index=False
        )

        print(
            "Using pre-extracted ECG/EGG features from baseline "
            f"({len(features_df)} subjects)"
        )
        print(f"Results saved to {METRICS_DIR}")


def _run_subject_classify(args):
    """Run subject-level temporal phenotype classification."""
    from analysis.prediction.early_cluster_predict import (
        compare_prefix_windows,
        run_subject_classification,
    )

    if args.compare_prefixes:
        comparison = compare_prefix_windows(
            baseline_path=args.baseline,
            output_dir=METRICS_DIR,
            prefix_windows=(0, 3, 5, 8, 20),
        )
        print("\nBest model by window:")
        print(comparison.to_string(index=False))
    else:
        result = run_subject_classification(
            baseline_path=args.baseline,
            output_dir=METRICS_DIR,
            prefix_minutes=args.prefix_minutes,
        )
        metrics = result["metrics"]
        print("\nSubject classification results:")
        print(metrics.to_string(index=False))
    print(f"Results saved to {METRICS_DIR}")


if __name__ == "__main__":
    main()
