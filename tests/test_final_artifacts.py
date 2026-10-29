"""Protect aggregate provenance, complete exports and non-overwriting behavior."""

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.final_artifacts import (
    early_recognition,
    group_sizes,
    load,
    module_table,
    read_rows,
    symptom_rules,
    verify_inputs,
)


class FinalArtifactTests(unittest.TestCase):
    def test_missing_and_external_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(FileNotFoundError):
                verify_inputs(root, {"inputs": ["missing.csv"]})
            with self.assertRaisesRegex(ValueError, "outside"):
                verify_inputs(root, {"inputs": ["../outside.csv"]})

    def test_recognition_does_not_substitute_balanced_accuracy(self):
        config = load(ROOT / "config/final_artifacts_20261023_v1.json")
        rows = read_rows(
            ROOT
            / config["prior_tables"]
            / "TableS10_partition_recovery_and_baseline.csv"
        )
        altered = [
            {**row, "median": "0.001"}
            if row["metric"] == "balanced_accuracy_equal_fold_mean"
            else row
            for row in rows
        ]
        self.assertEqual(early_recognition(rows), early_recognition(altered))
        with self.assertRaisesRegex(ValueError, "all 16"):
            early_recognition([row for row in rows if row["prefix"] != "8.0"])

    def test_conflicting_reference_group_sizes_are_rejected(self):
        config = load(ROOT / "config/final_artifacts_20261023_v1.json")
        rows = load(
            ROOT / config["prior_aggregates"] / "python_remaining/cluster_summary.json"
        )
        contradictory = {**rows[0], "reference_cluster_sizes": [1, 1]}
        with self.assertRaisesRegex(ValueError, "disagree"):
            group_sizes(rows + [contradictory])

    def test_rule_definitions_are_not_executed_and_zero_counts_survive(self):
        config = load(ROOT / "config/final_artifacts_20261023_v1.json")
        rows = read_rows(
            ROOT / config["prior_tables"] / "TableS2_recorded_codes_all139.csv"
        )
        code = (ROOT / config["rule_definitions"]).read_text()
        result = symptom_rules(
            code + '\nraise RuntimeError("must not execute")\n', rows
        )
        self.assertEqual(len(result), 10)
        zero = next(row for row in result if row["rule"] == "Functional Heartburn")
        self.assertEqual(int(zero["count"]), 0)
        self.assertEqual(int(zero["denominator_people"]), 204)

    def test_final_budgets_are_distinct_from_historical_plans(self):
        config = load(ROOT / "config/final_artifacts_20261023_v1.json")
        rows = read_rows(ROOT / config["prior_tables"] / "TableS1_all18_modules.csv")
        final = {
            row["module_id"]: row
            for row in module_table(ROOT, rows, config["module_reporting"])
        }
        self.assertEqual(float(final["U07"]["historical_planned_replicates"]), 20000)
        self.assertEqual(
            final["U07"]["actual_bootstrap_replicates_per_specification"], 200000
        )
        self.assertEqual(
            final["U03"]["actual_complete_fpca_replicates_per_interval"], 100000
        )
        self.assertEqual(
            final["U03"]["actual_sparse_fpca_replicates_per_specification"], 5000
        )
        self.assertEqual(final["U13"]["validation_repeats"], 20)
        self.assertEqual(
            final["U13"]["actual_bootstrap_replicates_per_specification"], ""
        )
        self.assertEqual(
            final["U16"]["actual_bootstrap_replicates_per_specification"], ""
        )


if __name__ == "__main__":
    unittest.main()
