"""Repair derived baseline fields and questionnaire placeholders."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


FIXED_INTAKE_TIME = 9.65


def _vas_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if col.startswith("VAS_") and col.endswith("min")]


def _calc_vas_avg(row: pd.Series, vas_cols: list[str]) -> float:
    values = []
    for col in vas_cols:
        raw = row[col]
        if pd.isna(raw):
            continue

        raw_str = str(raw).strip()
        if raw_str in {"E", "T"}:
            break

        value = pd.to_numeric(raw_str, errors="coerce")
        if pd.isna(value) or value == 0:
            continue
        values.append(float(value))

    if not values:
        return 0.0
    return round(float(np.mean(values)), 3)


def repair_baseline(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    repaired = df.copy()
    stats: dict[str, int] = {}

    vas_cols = _vas_columns(repaired)
    repaired["VAS_Avg."] = repaired.apply(_calc_vas_avg, axis=1, vas_cols=vas_cols)
    stats["vas_avg_recomputed"] = len(repaired)

    intake_yes = repaired["Recent_spicy_intake_24h"] == 1
    intake_no = repaired["Recent_spicy_intake_24h"] == 0

    intake_evidence = intake_no & (
        (repaired["Spicy_episodes_24h"] > 0) | (repaired["AES"] > 0)
    )
    repaired.loc[intake_evidence, "Recent_spicy_intake_24h"] = 1.0
    stats["recent_intake_corrected_to_yes"] = int(intake_evidence.sum())

    intake_no = repaired["Recent_spicy_intake_24h"] == 0
    repaired.loc[intake_no, "Time_since_last_intake_h"] = np.nan
    repaired.loc[intake_no, "Spicy_episodes_24h"] = 0.0
    repaired.loc[intake_no, "AES"] = 0.0
    stats["intake_no_rows_normalized"] = int(intake_no.sum())

    intake_yes = repaired["Recent_spicy_intake_24h"] == 1
    fixed_time = intake_yes & repaired["Time_since_last_intake_h"].eq(FIXED_INTAKE_TIME)
    repaired.loc[fixed_time, "Time_since_last_intake_h"] = np.nan
    stats["fixed_intake_time_cleared"] = int(fixed_time.sum())

    zero_episodes_yes = intake_yes & repaired["Spicy_episodes_24h"].eq(0)
    repaired.loc[zero_episodes_yes, "Spicy_episodes_24h"] = np.nan
    stats["intake_yes_zero_episodes_cleared"] = int(zero_episodes_yes.sum())

    return repaired, stats


def repair_csv(path: Path) -> dict[str, int]:
    df = pd.read_csv(path)
    repaired, stats = repair_baseline(df)
    repaired.to_csv(path, index=False, encoding="utf-8-sig")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair BaselineData-derived fields.")
    parser.add_argument("csv_paths", nargs="+", help="CSV files to repair in place")
    args = parser.parse_args()

    for raw_path in args.csv_paths:
        path = Path(raw_path)
        stats = repair_csv(path)
        print(path)
        for key, value in stats.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
