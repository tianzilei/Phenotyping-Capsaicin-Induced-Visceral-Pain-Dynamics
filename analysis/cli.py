"""Unified command-line entry point for the manuscript analysis workflow."""

import argparse
import os

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import matplotlib
import numpy as np
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

GENERATE_STANDALONE_FIGURES = False


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
    ecg_parser.add_argument(
        "--skip-classification",
        action="store_true",
        help="Only export ECG/EGG features and skip phenotype classification",
    )

    # Baseline phenotype prediction command
    cluster_pred_parser = subparsers.add_parser(
        "cluster-predict",
        help="Predict phenotype from baseline demographics and physiology",
    )
    cluster_pred_parser.add_argument(
        "--n-splits", type=int, default=10, help="Number of stratified CV folds"
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

    pipeline_parser = subparsers.add_parser(
        "pipeline", help="Run the full reproducible manuscript analysis pipeline"
    )
    pipeline_parser.add_argument(
        "--re-extract-ecg-egg",
        action="store_true",
        help="Re-extract ECG/EGG features from raw signals before classification",
    )
    pipeline_parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Skip final figure generation",
    )
    pipeline_parser.add_argument(
        "--skip-tables",
        action="store_true",
        help="Skip final table generation",
    )
    pipeline_parser.add_argument(
        "--skip-baseline-report",
        action="store_true",
        help="Skip the final baseline report generation",
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
    elif args.command == "cluster-predict":
        _run_cluster_predict(args)
    elif args.command == "subject-classify":
        _run_subject_classify(args)
    elif args.command == "tables":
        _run_tables(args)
    elif args.command == "baseline-report":
        _run_baseline_report(args)
    elif args.command == "figures":
        _run_figures(args)
    elif args.command == "pipeline":
        _run_pipeline(args)


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

    from analysis.figures.manuscript import clean_figure_outputs, make_figure_map

    figure_map = make_figure_map(args.baseline)

    if target_figures:
        for fig_num in target_figures:
            if fig_num in figure_map:
                filename, gen_fn = figure_map[fig_num]
                gen_fn(os.path.join(output_dir, filename))
            else:
                print(f"Unknown figure number: {fig_num}. Available: 1-16")
                continue
    else:
        clean_figure_outputs(output_dir)
        for filename, gen_fn in figure_map.values():
            gen_fn(os.path.join(output_dir, filename))

    print(f"\nManuscript figures saved to {output_dir}")


def _run_trajectory(args):
    """Run trajectory analysis."""
    from analysis.data_loader import get_vas_columns, load_unified_baseline
    from analysis.trajectory import change_point, clustering, plotting, survival

    baseline_df = load_unified_baseline(args.baseline)
    vas_cols = get_vas_columns(baseline_df)

    figures_dir = FIGURES_DIR
    os.makedirs(figures_dir, exist_ok=True)

    output_csv = os.path.join(METRICS_DIR, "trajectory_clustered.csv")

    vas_df = baseline_df[["ID"] + vas_cols].copy()
    time_cols = get_vas_columns(vas_df)

    if args.method in ("dtw-kmeans", "all"):
        print("Running DTW-KMeans clustering...")
        X, X_raw, scaler = clustering.prepare_vas_data(
            vas_df, time_cols, tail_fill="carry_forward"
        )
        labels, centroids, model = clustering.dtw_kmeans_cluster(
            X, n_clusters=args.n_clusters
        )

        baseline_df["cluster"] = labels
        baseline_df.to_csv(output_csv, index=False)

        sil_avg, sil_values = clustering.compute_dtw_silhouette(X, labels)
        print(f"Silhouette score: {sil_avg:.4f}")

        if not args.no_plot and GENERATE_STANDALONE_FIGURES:
            plotting.plot_cluster_centroids(
                centroids,
                labels,
                save_path=os.path.join(figures_dir, "cluster_centroids.png"),
            )

    if args.method in ("fuzzy-cmedoids", "all"):
        print("Running Fuzzy C-Medoids clustering...")
        X, X_raw, scaler = clustering.prepare_vas_data(
            vas_df, time_cols, tail_fill="carry_forward"
        )
        labels, memberships, medoid_indices = clustering.fuzzy_c_medoids(
            X, n_clusters=args.n_clusters
        )

        baseline_df["cluster"] = labels
        baseline_df.to_csv(output_csv, index=False)

    # Change point detection
    print("Running change point detection...")
    vas_wide = clustering.clean_vas_table(baseline_df, vas_cols)
    vas_wide.index = baseline_df["ID"]
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
    survival_input = clustering.clean_vas_table(baseline_df, vas_cols)
    time_values = np.array(
        [int(c.replace("VAS_", "").replace("min", "")) for c in vas_cols]
    )
    km_result = survival.compute_km_curves(
        survival_input.values,
        time_values=time_values,
        onset_thresh=3.0,
    )
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
    if np.isfinite(median_relief):
        median_relief_text = f"{median_relief} min"
    else:
        median_relief_text = "not reached within observed follow-up"
    print(f"Survival: median relief={median_relief_text}")
    print(km_result["comparison_note"])

    if not args.no_plot and GENERATE_STANDALONE_FIGURES:
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
    if not args.no_plot and GENERATE_STANDALONE_FIGURES:
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

    if not args.no_plot and GENERATE_STANDALONE_FIGURES:
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
    rome_results.to_csv(
        os.path.join(METRICS_DIR, "textmining_rome_subject_summary.csv"), index=False
    )
    print("Rome IV mapping saved to metrics/textmining_rome_subject_summary.csv")

    print(f"Results saved to {METRICS_DIR}")
    if not args.no_plot and GENERATE_STANDALONE_FIGURES:
        print(f"Figures saved to {figures_dir}")


def _run_fusion(args):
    """Run network fusion analysis."""
    from analysis.data_loader import load_analysis_ready_baseline

    baseline_df = load_analysis_ready_baseline(args.baseline)

    symptom_cols = ["Region_code", "Symptom_codes"]
    available_cols = [c for c in symptom_cols if c in baseline_df.columns]

    if not available_cols:
        print("No symptom columns found in baseline data.")
        return

    cols_to_include = ["ID"] + available_cols
    if "cluster" in baseline_df.columns:
        cols_to_include.append("cluster")
    else:
        raise ValueError("Fusion requires cluster labels; run trajectory first.")

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
        fusion_df,
        cluster_col="cluster",
        id_col="ID",
        symptom_col="Symptom",
        region_col="Region",
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

    def _mode_or_nan(series: pd.Series):
        mode = series.mode(dropna=True)
        return mode.iloc[0] if not mode.empty else np.nan

    baseline_df = load_unified_baseline(args.baseline)
    vas_cols = get_vas_columns(baseline_df)
    time_cols = vas_cols

    figures_dir = FIGURES_DIR
    os.makedirs(figures_dir, exist_ok=True)

    regression_subject_preds = None
    classification_subject_preds = None

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

        if not args.no_plot and GENERATE_STANDALONE_FIGURES:
            plotting.plot_observed_vs_predicted(
                preds,
                save_path=os.path.join(figures_dir, "regression_scatter.png"),
            )

        regression_subject_preds = (
            preds.groupby("subject_id", as_index=False)
            .agg({"predicted": "mean", "target": "mean"})
            .rename(
                columns={
                    "subject_id": "ID",
                    "predicted": "predicted_vas_delta",
                    "target": "target_vas_delta",
                }
            )
        )
        regression_subject_preds["delta_model"] = "Ridge"

    if args.task in ("classification", "both"):
        print("Building classification dataset...")
        data, y_col = classification.build_direction_dataset(
            baseline_df,
            time_cols,
            window=args.window,
            include_cluster=False,
            include_phenotype=True,
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

        subject_level_preds = preds[preds["model"] == "Logistic"].copy()
        if subject_level_preds.empty:
            subject_level_preds = preds.copy()

        classification_subject_preds = (
            subject_level_preds.groupby("subject_id", as_index=False)
            .agg(
                predicted_direction=("predicted", _mode_or_nan),
                target_direction=("target", _mode_or_nan),
            )
            .rename(columns={"subject_id": "ID"})
        )
        classification_subject_preds["direction_model"] = (
            subject_level_preds["model"].mode(dropna=True).iloc[0]
            if not subject_level_preds["model"].mode(dropna=True).empty
            else "unknown"
        )

    subject_frames = [
        frame
        for frame in [regression_subject_preds, classification_subject_preds]
        if frame is not None
    ]
    if subject_frames:
        subject_preds = subject_frames[0]
        for frame in subject_frames[1:]:
            subject_preds = subject_preds.merge(frame, on="ID", how="outer")

        subject_preds.to_csv(
            os.path.join(METRICS_DIR, "prediction_subject_level.csv"), index=False
        )
        print(
            "Prediction subject summaries saved to metrics/prediction_subject_level.csv"
        )

    print(f"Results saved to {METRICS_DIR}")
    if not args.no_plot and GENERATE_STANDALONE_FIGURES:
        print(f"Figures saved to {figures_dir}")


def _run_ecg_egg(args):
    """Run ECG/EGG analysis."""
    from analysis.data_loader import (
        ECG_EGG_FEATURE_COLUMNS,
        load_analysis_ready_baseline,
    )

    baseline_df = load_analysis_ready_baseline(args.baseline)

    figures_dir = FIGURES_DIR
    os.makedirs(figures_dir, exist_ok=True)

    if args.re_extract:
        raise RuntimeError(
            "Raw ECG/EGG signal feature extraction is not available in this repository. "
            "Run without --re-extract to export precomputed ECG/EGG features and "
            "classify phenotypes."
        )
    else:
        ecg_egg_cols = [
            "ID",
            "Sex",
            "Age",
            "BMI",
            "Height_cm",
            "Weight_kg",
            "cluster",
            *ECG_EGG_FEATURE_COLUMNS,
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

    if args.skip_classification:
        print("Skipped ECG/EGG phenotype classification.")
        return

    from analysis.prediction.ecg_egg_cluster import run_ecg_egg_cluster_classification

    run_ecg_egg_cluster_classification(
        baseline_path=args.baseline,
        output_dir=METRICS_DIR,
    )
    print("ECG/EGG phenotype classification saved to metrics outputs.")


def _run_cluster_predict(args):
    """Run baseline phenotype prediction."""
    from analysis.prediction.cluster_predict import run_cluster_prediction

    run_cluster_prediction(
        baseline_path=args.baseline,
        output_dir=METRICS_DIR,
        n_splits=args.n_splits,
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


def _run_pipeline(args):
    """Run the full manuscript analysis pipeline in a fixed order."""
    final_steps = []
    if not args.skip_baseline_report:
        final_steps.append(("Baseline report", _run_baseline_report))
    if not args.skip_tables:
        final_steps.append(("Manuscript tables", _run_tables))
    if not args.skip_figures:
        final_steps.append(("Manuscript figures", _run_figures))

    pipeline_steps = [
        (
            "Trajectory clustering, change points, and survival",
            _run_trajectory,
            argparse.Namespace(
                baseline=args.baseline,
                method="dtw-kmeans",
                n_clusters=3,
                no_plot=True,
            ),
        ),
        (
            "Text mining and Rome IV mapping",
            _run_textmining,
            argparse.Namespace(
                baseline=args.baseline,
                no_plot=True,
            ),
        ),
        (
            "Short-term VAS direction prediction",
            _run_predict,
            argparse.Namespace(
                baseline=args.baseline,
                task="classification",
                window=3,
                no_plot=True,
            ),
        ),
        (
            "ECG/EGG feature export and classification",
            _run_ecg_egg,
            argparse.Namespace(
                baseline=args.baseline,
                data_dir=ECG_EGG_DATA_DIR,
                no_plot=True,
                re_extract=args.re_extract_ecg_egg,
                skip_classification=False,
            ),
        ),
        (
            "Baseline phenotype prediction",
            _run_cluster_predict,
            argparse.Namespace(
                baseline=args.baseline,
                n_splits=10,
            ),
        ),
        (
            "Early-window phenotype classification",
            _run_subject_classify,
            argparse.Namespace(
                baseline=args.baseline,
                prefix_minutes=8,
                compare_prefixes=True,
            ),
        ),
        (
            "Network fusion",
            _run_fusion,
            argparse.Namespace(
                baseline=args.baseline,
                no_plot=True,
            ),
        ),
    ]

    total_steps = len(pipeline_steps) + len(final_steps)

    for index, (label, runner, runner_args) in enumerate(pipeline_steps, start=1):
        print(f"\n[{index}/{total_steps}] {label}")
        runner(runner_args)

    next_step = len(pipeline_steps) + 1

    if not args.skip_baseline_report:
        print(f"\n[{next_step}/{total_steps}] Baseline report")
        _run_baseline_report(argparse.Namespace(baseline=args.baseline))
        next_step += 1

    if not args.skip_tables:
        print(f"\n[{next_step}/{total_steps}] Manuscript tables")
        _run_tables(
            argparse.Namespace(
                baseline=args.baseline,
                output_dir=METRICS_DIR,
            )
        )
        next_step += 1

    if not args.skip_figures:
        print(f"\n[{next_step}/{total_steps}] Manuscript figures")
        _run_figures(
            argparse.Namespace(
                baseline=args.baseline,
                output_dir=FIGURES_DIR,
                figures=None,
            )
        )

    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
