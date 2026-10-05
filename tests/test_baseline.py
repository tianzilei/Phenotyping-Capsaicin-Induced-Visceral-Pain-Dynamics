import csv
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from capsaicin.baseline import (
    BaselinePreparationError,
    prepare_baseline_rows,
    write_baseline_copy,
)


class BaselinePreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "source.csv"

    def write_rows(self, rows):
        with self.source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["ID", "Recent_spicy_intake_24h", "Time_since_last_intake_h", "other"]
            )
            writer.writerows(rows)

    def test_conditional_blank_becomes_explicit_na(self):
        self.write_rows([["SYN001", "0.0", "", "keep"], ["SYN002", "1.0", "7", "same"]])
        fields, rows, counts = prepare_baseline_rows(self.source)
        self.assertEqual(rows[0]["Time_since_last_intake_h"], "NA")
        self.assertEqual(
            rows[0]["Time_since_last_intake_h_status"],
            "not_applicable_no_recent_intake",
        )
        self.assertEqual(rows[1]["Time_since_last_intake_h"], "7")
        self.assertEqual(rows[1]["other"], "same")
        self.assertEqual(fields[-1], "Time_since_last_intake_h_status")
        self.assertEqual(counts["filled_na_not_applicable"], 1)

    def test_missing_time_with_recent_intake_fails(self):
        self.write_rows([["SYN001", "1", "", "x"]])
        with self.assertRaises(BaselinePreparationError):
            prepare_baseline_rows(self.source)

    def test_conflicting_time_without_recent_intake_fails(self):
        self.write_rows([["SYN001", "0", "5", "x"]])
        with self.assertRaises(BaselinePreparationError):
            prepare_baseline_rows(self.source)

    def test_source_is_unchanged_and_output_is_not_overwritten(self):
        self.write_rows([["SYN001", "0", "", "x"]])
        before = self.source.read_bytes()
        destination = Path(self.tmp.name) / "new" / "copy.csv"
        write_baseline_copy(self.source, destination)
        self.assertEqual(self.source.read_bytes(), before)
        with self.assertRaises(BaselinePreparationError):
            write_baseline_copy(self.source, destination)


if __name__ == "__main__":
    unittest.main()
