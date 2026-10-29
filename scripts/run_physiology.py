"""Fit one explicitly prepared repeated-block model into a new private directory."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.physiology import fit, prepare, row_of


def run(input_path, output, outcome, predictors):
    import pandas as pd

    output = Path(output).resolve()
    if output.is_relative_to(ROOT):
        raise ValueError(
            "Individual model outputs require a directory outside the repository"
        )
    if output.exists():
        raise FileExistsError(output)
    data = pd.read_csv(input_path)
    prepared = prepare(data, outcome, predictors)
    if prepared["G"] < 2 or prepared["N"] <= prepared["absorbed"] + prepared["K"]:
        raise ValueError("Insufficient participants or residual degrees of freedom")
    result = fit(prepared)
    output.mkdir(parents=True, exist_ok=False)
    pd.DataFrame(
        [
            {"predictor": name, **row_of(prepared, result, j)}
            for j, name in enumerate(predictors)
        ]
    ).to_csv(output / "coefficients.csv", index=False, mode="x")
    (output / "settings.json").write_text(
        json.dumps(
            {
                "outcome": outcome,
                "predictors": predictors,
                "participant_column": "person_id",
                "block_column": "block",
                "covariance": "CR1 with CRV3 sensitivity",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--predictor", action="append", required=True)
    args = parser.parse_args()
    run(args.input, args.output, args.outcome, args.predictor)
