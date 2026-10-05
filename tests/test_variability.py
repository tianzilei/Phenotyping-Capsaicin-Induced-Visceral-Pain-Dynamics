import copy
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from capsaicin.variability import window_metrics


def fixture(values):
    return [
        dict(
            time_min=t,
            vas=v if isinstance(v, (int, float)) else None,
            status="observed" if isinstance(v, (int, float)) else v,
        )
        for t, v in enumerate(values, 1)
    ]


class VariabilityTests(unittest.TestCase):
    def test_gap_termination_and_window_boundaries(self):
        rows = fixture([0, 2, "missing", 6, 8, "E", "E"])
        before = copy.deepcopy(rows)
        z = window_metrics(rows, 1, 7)
        self.assertEqual(z["n_pairs"], 2)
        self.assertEqual(z["mssd"], 4)
        self.assertEqual(z["centered_change_ms"], 0)
        self.assertFalse(z["eligible"])
        self.assertEqual(window_metrics(rows, 2, 4)["n_pairs"], 0)
        self.assertEqual(rows, before)

    def test_decomposition_with_opposite_changes(self):
        z = window_metrics(fixture([1, 3, 2, 6]), 1, 4)
        self.assertTrue(z["complete"])
        self.assertTrue(z["eligible"])
        self.assertEqual(z["mssd"], 7)
        self.assertAlmostEqual(
            z["mssd"], z["mean_adjacent_change"] ** 2 + z["centered_change_ms"]
        )

    def test_zero_is_distinct_from_undefined(self):
        z = window_metrics(fixture([0, 0, 0, 0]), 1, 4)
        self.assertEqual(z["mssd"], 0)
        self.assertEqual(z["sample_sd"], 0)
        self.assertIsNone(window_metrics(fixture([0, "T"]), 1, 2)["mssd"])
        self.assertIsNone(window_metrics(fixture(["E", "E"]), 1, 2)["mean_vas"])

    def test_duplicate_and_bad_observed_rejected(self):
        with self.assertRaises(ValueError):
            window_metrics(fixture([0]) * 2, 1, 1)
        with self.assertRaises(ValueError):
            window_metrics(fixture([float("nan")]), 1, 1)
