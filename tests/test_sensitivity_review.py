import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from review_sensitivity_readonly import verify_tables


class SensitivityReviewTests(unittest.TestCase):
    def fixture(self):
        raw = [
            dict(
                path="synthetic",
                channel="0",
                window_index="0",
                amplitude_multiplier=str(a),
                energy_multiplier=str(a),
                amplitude_candidates="0",
                energy_candidates="0",
                matched="0",
                agreement="",
            )
            for a in (2, 3, 4, 5)
        ]
        base = [
            dict(
                path="synthetic",
                channel="0",
                window_index="0",
                amplitude_candidate_count="0",
                energy_candidate_count="0",
                matched="0",
                agreement="",
            )
        ]
        summ = [
            dict(
                amplitude_multiplier=str(a),
                energy_multiplier=str(a),
                channel_windows="1",
                amplitude_candidates="0",
                energy_candidates="0",
                median_agreement="",
                low_agreement_fraction="",
            )
            for a in (2, 3, 4, 5)
        ]
        return raw, [], summ, base, []

    def test_empty_detection_not_perfect_agreement(self):
        data = self.fixture()
        result, _ = verify_tables(*data)
        self.assertEqual(result["baseline_window_matches"], 1)
        data[0][0]["agreement"] = "1"
        with self.assertRaises(AssertionError):
            verify_tables(*data)

    def test_duplicate_or_missing_scenario_rejected(self):
        for mutation in ("duplicate", "missing"):
            data = self.fixture()
            if mutation == "duplicate":
                data[0].append(copy.copy(data[0][0]))
            else:
                data[0].pop()
            with self.assertRaises(AssertionError):
                verify_tables(*data)

    def test_baseline_mismatch_rejected(self):
        data = self.fixture()
        data[3][0]["amplitude_candidate_count"] = "1"
        with self.assertRaises(AssertionError):
            verify_tables(*data)
