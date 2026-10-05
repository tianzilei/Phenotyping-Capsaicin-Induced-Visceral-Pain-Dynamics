import unittest
from capsaicin.rest_relative_deviation import bootstrap_delta_summary, paired_delta


class RestRelativeDeviationTests(unittest.TestCase):
    def test_delta_preserves_missing(self):
        rows = [
            {"rest_x": "1", "stimulus_x": "3"},
            {"rest_x": "", "stimulus_x": "2"},
            {"rest_x": "2", "stimulus_x": "nan"},
        ]
        self.assertEqual(paired_delta(rows, "x").tolist(), [2.0])

    def test_bootstrap_reproducible(self):
        self.assertEqual(
            bootstrap_delta_summary([1, 2, 3], replicates=50),
            bootstrap_delta_summary([1, 2, 3], replicates=50),
        )


if __name__ == "__main__":
    unittest.main()
