"""Export restricted individual copies to a new directory outside every Git checkout."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.privacy import BASELINE_FIELDS, PrivacyError, deidentify, read_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Structured baseline CSV")
    source.add_argument(
        "--policy",
        type=Path,
        help="Private JSON list of explicit linked-table export policies",
    )
    parser.add_argument(
        "--aliases",
        type=Path,
        help="Private, already confirmed source-ID to canonical-ID JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New Git-external restricted directory",
    )
    args = parser.parse_args()
    try:
        if args.policy:
            tables = json.loads(args.policy.read_text(encoding="utf-8"))
        else:
            fields, _ = read_table(args.input)
            tables = [
                dict(
                    input=str(args.input),
                    output_name="baseline_pseudonymized.csv",
                    keep_columns=[f for f in BASELINE_FIELDS if f in fields],
                    id_columns=["ID"],
                    primary_id="ID",
                )
            ]
        aliases = (
            json.loads(args.aliases.read_text(encoding="utf-8"))
            if args.aliases
            else None
        )
        result = deidentify(tables, args.output, aliases)
        print(
            json.dumps(
                dict(
                    status=result["status"],
                    output=str(args.output.resolve()),
                    tables=len(result["tables"]),
                    canonical_people=result["canonical_people"],
                )
            )
        )
    except (PrivacyError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Export refused: {exc}\n")


if __name__ == "__main__":
    main()
