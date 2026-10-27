"""Build the current 4/6 figures and 2/29 tables from reviewed public aggregates."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.final_artifacts import build as historical_build
from capsaicin.aligned_artifacts import build as aligned_build
from capsaicin.final_artifacts import load


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/aligned_artifacts_20261027_v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = load(args.config)
    build = (
        aligned_build
        if config["version"] == "aligned_artifacts_20261027_v1"
        else historical_build
    )
    build(ROOT, args.config, args.output)
