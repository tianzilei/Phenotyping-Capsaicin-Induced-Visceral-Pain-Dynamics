"""Generate a focused analysis report from the unified baseline CSV."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.constants import (
    CLUSTER_LABEL_MAP,
    FIGURES_DIR,
    METRICS_DIR,
    REGION_CODE_MAP,
    SUBJECT_INFO_FILE,
    SYMPTOM_CODE_MAP,
)
from analysis.data_loader import get_vas_columns, load_analysis_ready_baseline
from analysis.parsing import map_codes, parse_compact_codes, parse_region_codes
from analysis.tables.baseline import generate_baseline_table
from analysis.tables.formatter import df_to_markdown
from analysis.tables.formatter import format_mean_sd, format_n_percent


def _ensure_dirs() -> None:
    Path(METRICS_DIR).mkdir(parents=True, exist_ok=True)
    Path(FIGURES_DIR).mkdir(parents=True, exist_ok=True)


def _as_numeric(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    return df.loc[:, list(cols)].apply(pd.to_numeric, errors="coerce")


def _fmt_mean_sd(values: pd.Series) -> str:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return ""
    return format_mean_sd(values)


def _fmt_median_iqr(values: pd.Series) -> str:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return ""
    q1 = values.quantile(0.25)
    q3 = values.quantile(0.75)
    return f"{values.median():.1f} ({q1:.1f}-{q3:.1f})"


def _fmt_count_pct(values: pd.Series, positive_value) -> str:
    clean = values.dropna()
    if clean.empty:
        return ""
    return format_n_percent(int((clean == positive_value).sum()), len(clean))


def _time_from_vas_col(col: str) -> int:
    return int(col.replace("VAS_", "").replace("min", ""))


def _build_vas_subject_summary(df: pd.DataFrame, vas_cols: list[str]) -> pd.DataFrame:
    vas_num = _as_numeric(df, vas_cols)
    times = np.array([_time_from_vas_col(c) for c in vas_cols], dtype=float)

    summary = pd.DataFrame({"ID": df["ID"]})
    summary["valid_vas_points"] = vas_num.notna().sum(axis=1)
    summary["vas_peak"] = vas_num.max(axis=1)
    summary["vas_min"] = vas_num.min(axis=1)
    summary["vas_range"] = summary["vas_peak"] - summary["vas_min"]
    summary["vas_mean"] = vas_num.mean(axis=1)

    peak_times = []
    auc_values = []
    for _, row in vas_num.iterrows():
        valid = row.notna().to_numpy()
        if not valid.any():
            peak_times.append(np.nan)
            auc_values.append(np.nan)
            continue
        row_values = row.to_numpy(dtype=float)
        peak_times.append(times[valid][np.nanargmax(row_values[valid])])
        if valid.sum() >= 2:
            auc_values.append(float(np.trapezoid(row_values[valid], times[valid])))
        else:
            auc_values.append(np.nan)
    summary["vas_peak_time_min"] = peak_times
    summary["vas_auc_1_20min"] = auc_values

    return summary


def _summarize_by_group(
    df: pd.DataFrame, subject_vas: pd.DataFrame, group_col: str
) -> pd.DataFrame:
    merged = df.merge(subject_vas, on="ID", how="left")
    rows = []
    for group, group_df in merged.groupby(group_col, dropna=False):
        label = "Missing" if pd.isna(group) else str(group)
        if group_col == "cluster":
            try:
                label = CLUSTER_LABEL_MAP.get(int(float(label)), label)
            except ValueError:
                pass
        rows.append(
            {
                group_col: label,
                "n": len(group_df),
                "female_n_pct": _fmt_count_pct(group_df["Sex"], "女")
                if "Sex" in group_df
                else "",
                "age_mean_sd": _fmt_mean_sd(group_df["Age"])
                if "Age" in group_df
                else "",
                "bmi_mean_sd": _fmt_mean_sd(group_df["BMI"])
                if "BMI" in group_df
                else "",
                "vas_avg_mean_sd": _fmt_mean_sd(group_df["VAS_Avg."])
                if "VAS_Avg." in group_df
                else "",
                "vas_peak_mean_sd": _fmt_mean_sd(group_df["vas_peak"]),
                "peak_time_median_iqr": _fmt_median_iqr(group_df["vas_peak_time_min"]),
                "ccei_mean_sd": _fmt_mean_sd(group_df["CCEI"])
                if "CCEI" in group_df
                else "",
                "aes_mean_sd": _fmt_mean_sd(group_df["AES"])
                if "AES" in group_df
                else "",
                "ecg_sqi_mean_sd": _fmt_mean_sd(group_df["ECG_SQI"])
                if "ECG_SQI" in group_df
                else "",
                "egg_sqi_mean_sd": _fmt_mean_sd(group_df["EGG_SQI"])
                if "EGG_SQI" in group_df
                else "",
            }
        )
    return pd.DataFrame(rows)


def _plot_vas_trajectory(
    df: pd.DataFrame, vas_cols: list[str], group_col: str, output_path: str
) -> None:
    vas_num = _as_numeric(df, vas_cols)
    times = np.array([_time_from_vas_col(c) for c in vas_cols])

    plt.figure(figsize=(8, 5))
    for group, idx in df.groupby(group_col, dropna=False).groups.items():
        label = "Missing" if pd.isna(group) else str(group)
        if group_col == "cluster":
            try:
                label = CLUSTER_LABEL_MAP.get(int(float(label)), label)
            except ValueError:
                pass
        group_vas = vas_num.loc[idx]
        mean = group_vas.mean(axis=0)
        sem = group_vas.sem(axis=0)
        plt.plot(times, mean, marker="o", linewidth=2, label=label)
        plt.fill_between(times, mean - sem, mean + sem, alpha=0.15)

    plt.xlabel("Time after capsaicin ingestion (min)")
    plt.ylabel("VAS pain score")
    plt.title(f"VAS trajectory by {group_col}")
    plt.xticks(times)
    plt.ylim(bottom=0)
    plt.grid(alpha=0.25)
    plt.legend(title=group_col)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def _categorical_summary(df: pd.DataFrame) -> pd.DataFrame:
    categorical_cols = [
        "Sex",
        "cluster",
        "Alcohol_consumption",
        "Recent_spicy_intake_24h",
        "Baseline_GI_symptoms",
        "top_rome_disease",
        "predicted_direction",
        "delta_model",
        "direction_model",
    ]
    rows = []
    for col in categorical_cols:
        if col not in df.columns:
            continue
        counts = df[col].value_counts(dropna=False)
        for value, count in counts.items():
            rows.append(
                {
                    "variable": col,
                    "level": "Missing" if pd.isna(value) else str(value),
                    "n": int(count),
                    "percent": round(count / len(df) * 100, 1),
                }
            )
    return pd.DataFrame(rows)


def _coded_value_summary(
    df: pd.DataFrame, source_col: str, code_map: dict, parser
) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        raw_value = row.get(source_col, "")
        codes = parser(str(raw_value), valid_codes=set(code_map.keys()))
        for code, label in zip(codes, map_codes(codes, code_map)):
            rows.append(
                {
                    "code": code,
                    "label": label,
                    "ID": row.get("ID"),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["code", "label", "n", "percent_of_participants"])

    exploded = pd.DataFrame(rows).drop_duplicates(["ID", "code"])
    summary = (
        exploded.groupby(["code", "label"], as_index=False)
        .size()
        .rename(columns={"size": "n"})
    )
    summary["percent_of_participants"] = (summary["n"] / len(df) * 100).round(1)
    return summary.sort_values(["n", "code"], ascending=[False, True])


def _data_quality_summary(df: pd.DataFrame, vas_cols: list[str]) -> pd.DataFrame:
    core_cols = [
        "ID",
        "Sex",
        "Age",
        "Height_cm",
        "Weight_kg",
        "BMI",
        "cluster",
        "VAS_Avg.",
    ]
    rows = []
    for col in [c for c in core_cols if c in df.columns] + vas_cols:
        raw = df[col]
        rows.append(
            {
                "column": col,
                "missing_n": int(raw.isna().sum()),
                "missing_percent": round(raw.isna().mean() * 100, 1),
                "non_numeric_n": int(pd.to_numeric(raw, errors="coerce").isna().sum())
                if col in vas_cols
                else "",
                "E_code_n": int((raw == "E").sum()) if col in vas_cols else "",
                "T_code_n": int((raw == "T").sum()) if col in vas_cols else "",
            }
        )
    return pd.DataFrame(rows)


def _numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    preferred = [
        "Age",
        "Height_cm",
        "Weight_kg",
        "BMI",
        "Spicy_food_frequency",
        "Usual_spiciness_level",
        "Spicy_food_preference",
        "Max_tolerable_spiciness",
        "CCEI",
        "Time_since_last_intake_h",
        "Spicy_episodes_24h",
        "AES",
        "Time_since_last_meal_h",
        "mean_HR",
        "SDNN",
        "RMSSD",
        "LF_HF_ratio",
        "ECG_SQI",
        "dominant_freq_cpm",
        "pct_normogastria",
        "EGG_SQI",
        "VAS_Avg.",
        "rome_match_score",
        "predicted_vas_delta",
        "target_vas_delta",
    ]
    cols = [c for c in preferred if c in df.columns]
    numeric = _as_numeric(df, cols)
    out = numeric.describe(percentiles=[0.25, 0.5, 0.75]).T
    out = out.rename(columns={"50%": "median"})
    return out.round(3).reset_index(names="variable")


def _write_report(
    df: pd.DataFrame,
    vas_time_summary: pd.DataFrame,
    cluster_summary: pd.DataFrame,
    region_summary: pd.DataFrame,
    symptom_summary: pd.DataFrame,
    data_quality: pd.DataFrame,
    output_path: str,
    figures: list[str],
) -> None:
    duplicate_ids = int(df["ID"].duplicated().sum()) if "ID" in df.columns else 0
    missing_core = data_quality.query("missing_n > 0").head(20)
    source_file = Path(SUBJECT_INFO_FILE)
    try:
        source_label = str(source_file.relative_to(Path.cwd()))
    except ValueError:
        source_label = source_file.name

    lines = [
        "# BaselineData.csv Analysis Report",
        "",
        "## Dataset",
        "",
        f"- Input file: `{source_label}`",
        f"- Participants: {len(df)}",
        f"- Variables: {df.shape[1]}",
        f"- Duplicate IDs: {duplicate_ids}",
        "",
        "## Table 1",
        "",
        generate_baseline_table(df).strip(),
        "",
        "## VAS Time-Course Summary",
        "",
        df_to_markdown(vas_time_summary).strip(),
        "",
        "## Summary by Cluster",
        "",
        df_to_markdown(cluster_summary).strip(),
        "",
        "## Region Code Summary",
        "",
        df_to_markdown(region_summary).strip(),
        "",
        "## Symptom Code Summary",
        "",
        df_to_markdown(symptom_summary).strip(),
        "",
        "## Data Quality Notes",
        "",
        "Columns with missing values or VAS stop/end codes are shown below.",
        "",
        df_to_markdown(missing_core).strip() if not missing_core.empty else "No missing values found in core columns.",
        "",
        "## Figures",
        "",
    ]
    lines.extend([f"- `{fig}`" for fig in figures])
    lines.append("")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def generate_report(baseline_path: str | None = None) -> dict[str, str]:
    _ensure_dirs()
    df = load_analysis_ready_baseline(baseline_path)
    vas_cols = sorted(get_vas_columns(df), key=_time_from_vas_col)

    subject_vas = _build_vas_subject_summary(df, vas_cols)
    vas_num = _as_numeric(df, vas_cols)
    vas_time_summary = pd.DataFrame(
        {
            "time_min": [_time_from_vas_col(c) for c in vas_cols],
            "n_valid": vas_num.notna().sum(axis=0).to_numpy(),
            "n_E_code": [(df[c] == "E").sum() for c in vas_cols],
            "n_T_code": [(df[c] == "T").sum() for c in vas_cols],
            "mean": vas_num.mean(axis=0).round(2).to_numpy(),
            "sd": vas_num.std(axis=0).round(2).to_numpy(),
            "median": vas_num.median(axis=0).round(2).to_numpy(),
            "q1": vas_num.quantile(0.25, axis=0).round(2).to_numpy(),
            "q3": vas_num.quantile(0.75, axis=0).round(2).to_numpy(),
        }
    )

    cluster_summary = _summarize_by_group(df, subject_vas, "cluster")
    region_summary = _coded_value_summary(
        df, "Region_code", REGION_CODE_MAP, parse_region_codes
    )
    symptom_summary = _coded_value_summary(
        df, "Symptom_codes", SYMPTOM_CODE_MAP, parse_compact_codes
    )
    data_quality = _data_quality_summary(df, vas_cols)

    outputs = {
        "report": str(Path(METRICS_DIR) / "baseline_data_analysis.md"),
        "numeric_summary": str(Path(METRICS_DIR) / "baseline_numeric_summary.csv"),
        "categorical_summary": str(Path(METRICS_DIR) / "baseline_categorical_summary.csv"),
        "vas_subject_summary": str(Path(METRICS_DIR) / "baseline_vas_subject_summary.csv"),
        "vas_time_summary": str(Path(METRICS_DIR) / "baseline_vas_time_summary.csv"),
        "cluster_summary": str(Path(METRICS_DIR) / "baseline_cluster_summary.csv"),
        "region_summary": str(Path(METRICS_DIR) / "baseline_region_code_summary.csv"),
        "symptom_summary": str(Path(METRICS_DIR) / "baseline_symptom_code_summary.csv"),
        "data_quality": str(Path(METRICS_DIR) / "baseline_data_quality.csv"),
    }

    _numeric_summary(df).to_csv(outputs["numeric_summary"], index=False, encoding="utf-8-sig")
    _categorical_summary(df).to_csv(outputs["categorical_summary"], index=False, encoding="utf-8-sig")
    subject_vas.to_csv(outputs["vas_subject_summary"], index=False, encoding="utf-8-sig")
    vas_time_summary.to_csv(outputs["vas_time_summary"], index=False, encoding="utf-8-sig")
    cluster_summary.to_csv(outputs["cluster_summary"], index=False, encoding="utf-8-sig")
    region_summary.to_csv(outputs["region_summary"], index=False, encoding="utf-8-sig")
    symptom_summary.to_csv(outputs["symptom_summary"], index=False, encoding="utf-8-sig")
    data_quality.to_csv(outputs["data_quality"], index=False, encoding="utf-8-sig")

    _write_report(
        df=df,
        vas_time_summary=vas_time_summary,
        cluster_summary=cluster_summary,
        region_summary=region_summary,
        symptom_summary=symptom_summary,
        data_quality=data_quality,
        output_path=outputs["report"],
        figures=[],
    )
    return outputs


if __name__ == "__main__":
    generated = generate_report()
    for name, path in generated.items():
        print(f"{name}: {path}")
