import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.contracts import ContractError, read_wide
from capsaicin.qc import subject_descriptives, time_counts
from capsaicin.cli import validate


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "input.csv"
        self.config = json.loads((ROOT / "config/synthetic.json").read_text())
        self.config["data"]["expected_minutes"] = [1, 2, 3, 4]

    def rows(self, values):
        with self.path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ID", "VAS_1min", "VAS_2min", "VAS_3min", "VAS_4min"])
            w.writerows(values)
        return read_wide(self.path, self.config)

    def test_termination_preserved_and_not_imputed(self):
        rows = self.rows([["s1", 3, 0, "E", ""], ["s2", 9, "T", "T", ""]])
        self.assertEqual(
            [r["status"] for r in rows[:4]],
            ["observed", "observed", "termination_E", "post_termination"],
        )
        self.assertTrue(
            all(r["vas"] is None for r in rows if r["status"] != "observed")
        )
        self.assertEqual(time_counts(rows)[1]["n_termination_T"], 1)

    def test_no_mssd_across_missing_minute(self):
        output = subject_descriptives(self.rows([["s1", 1, "", 8, 10]]))[0]
        self.assertEqual(output["n_adjacent_pairs"], 1)
        self.assertEqual(output["raw_mssd"], 4)

    def test_all_missing_not_zero(self):
        output = subject_descriptives(self.rows([["s1", "", "NA", "", ""]]))[0]
        self.assertEqual(output["n_observed"], 0)
        self.assertIsNone(output["raw_mssd"])
        self.assertIsNone(output["mean_observed_vas"])

    def test_bad_tokens_values_and_post_termination_fail(self):
        for values in [
            [0, "bad", 0, 0],
            [0, "inf", 0, 0],
            [0, 11, 0, 0],
            [0, -1, 0, 0],
            [0, "E", 1, ""],
            [0, "E", "T", ""],
        ]:
            with self.subTest(values=values), self.assertRaises(ContractError):
                self.rows([["s1"] + values])

    def test_duplicate_or_empty_subject_id_fails(self):
        for values in [[["s1", 1, 2, 3, 4]] * 2, [["", 1, 2, 3, 4]]]:
            with self.subTest(values=values), self.assertRaises(ContractError):
                self.rows(values)

    def test_unknown_scale_fails(self):
        self.config["data"]["vas_max"] = None
        with self.assertRaises(ContractError):
            self.rows([["s1", 1, 2, 3, 4]])

    def test_missing_column_fails(self):
        self.path.write_text("ID,VAS_1min\ns1,2\n")
        with self.assertRaises(ContractError):
            read_wide(self.path, self.config)

    def test_duplicate_header_fails(self):
        self.path.write_text("ID,VAS_1min,VAS_1min,VAS_3min,VAS_4min\ns1,1,2,3,4\n")
        with self.assertRaises(ContractError):
            read_wide(self.path, self.config)

    def test_minute_columns_sorted_numerically(self):
        self.config["data"]["expected_minutes"] = [1, 2, 10]
        self.path.write_text("ID,VAS_10min,VAS_2min,VAS_1min\ns1,5,3,1\n")
        rows = read_wide(self.path, self.config)
        self.assertEqual([r["time_min"] for r in rows], [1, 2, 10])
        self.assertEqual([r["vas"] for r in rows], [1, 3, 5])

    def test_output_refuses_overwrite_and_input_unchanged(self):
        self.rows([["s1", 1, 2, "E", ""]])
        before = self.path.read_bytes()
        config_path = Path(self.tmp.name) / "config.json"
        config_path.write_text(json.dumps(self.config))
        output = Path(self.tmp.name) / "run"
        validate(self.path, config_path, output, synthetic=True)
        self.assertEqual(self.path.read_bytes(), before)
        manifest = json.loads((output / "run_manifest.json").read_text())
        self.assertTrue(manifest["synthetic"])
        with self.assertRaises(ContractError):
            validate(self.path, config_path, output, synthetic=True)

    def test_synthetic_config_cannot_be_used_for_real_validation(self):
        self.rows([["s1", 1, 2, 3, 4]])
        config_path = Path(self.tmp.name) / "config.json"
        config_path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractError):
            validate(self.path, config_path)


if __name__ == "__main__":
    unittest.main()
