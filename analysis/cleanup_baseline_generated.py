"""Move generated analysis outputs out of BaselineData.csv."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from analysis.constants import METRICS_DIR, SUBJECT_INFO_FILE
from analysis.data_loader import ECG_EGG_FEATURE_COLUMNS, strip_generated_columns

ROME_COLUMNS = ["top_rome_disease", "rome_match_score"]
PREDICTION_COLUMNS = [
    "predicted_vas_delta",
    "target_vas_delta",
    "predicted_direction",
    "prediction_model",
    "target_direction",
    "delta_model",
    "direction_model",
]


def _write_if_present(df: pd.DataFrame, columns: list[str], path: Path) -> int:
    keep = ["ID"] + [col for col in columns if col in df.columns]
    if len(keep) == 1:
        return 0
    subset = df[keep].copy()
    if len(keep) > 1:
        subset.to_csv(path, index=False, encoding="utf-8-sig")
    return len(subset)


def cleanup_baseline(baseline_path: str) -> dict[str, int]:
    baseline = pd.read_csv(baseline_path)
    stripped = strip_generated_columns(baseline)
    metrics_dir = Path(METRICS_DIR)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "ecg_egg_rows_exported": _write_if_present(
            baseline, ECG_EGG_FEATURE_COLUMNS, metrics_dir / "ecg_egg_features.csv"
        ),
        "rome_rows_exported": _write_if_present(
            baseline, ROME_COLUMNS, metrics_dir / "textmining_rome_subject_summary.csv"
        ),
        "prediction_rows_exported": _write_if_present(
            baseline, PREDICTION_COLUMNS, metrics_dir / "prediction_subject_level.csv"
        ),
    }

    cluster_cols = ["ID"]
    if "cluster" in baseline.columns:
        cluster_cols.append("cluster")
    if len(cluster_cols) > 1:
        stripped.merge(baseline[cluster_cols], on="ID", how="left").to_csv(
            metrics_dir / "trajectory_clustered.csv",
            index=False,
            encoding="utf-8-sig",
        )
        stats["cluster_rows_exported"] = len(baseline)
    else:
        stats["cluster_rows_exported"] = 0

    stripped.to_csv(baseline_path, index=False, encoding="utf-8-sig")
    stats["baseline_rows_cleaned"] = len(stripped)
    stats["generated_columns_removed"] = len(
        [col for col in baseline.columns if col not in stripped.columns]
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Move generated analysis outputs out of BaselineData.csv."
    )
    parser.add_argument(
        "--baseline",
        default=SUBJECT_INFO_FILE,
        help="Path to BaselineData.csv",
    )
    args = parser.parse_args()

    stats = cleanup_baseline(args.baseline)
    print(args.baseline)
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
