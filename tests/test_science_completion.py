"""Only synthetic edge cases; no participant input in tests."""

import sys
from pathlib import Path
import unittest
import io
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from capsaicin.science_completion import finite_design, evaluate, execute_batch


class ScienceCompletionTests(unittest.TestCase):
    def test_gap_blocks_even_when_both_endpoints_are_valid(self):
        y = np.array([[1, np.nan, 3, 4], [0, 1, 2, 3], [1, 1, 1, 1]], float)
        mask, d, meta = finite_design(y, (2,))
        self.assertEqual(mask[:, 0].tolist(), [False, False])
        self.assertEqual(meta[0]["people"], 2)
        prepared = dict(support=mask, change=d, h=np.array([2, 2]))
        result = evaluate("finite_changes", prepared, np.ones((1, 3), int))[0]
        self.assertEqual(result[0], 1.0)
        self.assertEqual(result[1], 0.0)  # generalized inverse median of [0,2]
        self.assertEqual(result[2], 0.5)
        self.assertEqual(result[4], 0.5)

    def test_empty_support_remains_undefined(self):
        mask, d, meta = finite_design([[1, np.nan, 2], [np.nan, 2, np.nan]], (2,))
        self.assertEqual(meta[0]["people"], 0)
        result = evaluate(
            "finite_changes", dict(support=mask, change=d, h=[2]), np.ones((1, 2), int)
        )
        self.assertTrue(np.isnan(result).all())

    def test_unrecorded_symptoms_not_negative_denominator(self):
        prepared = dict(
            numerator=np.array([[1, 0, 0]], int), denominator=np.array([[1, 1, 0]], int)
        )
        self.assertEqual(
            evaluate("symptoms", prepared, np.ones((1, 3), int))[0, 0], 0.5
        )
        self.assertTrue(
            np.isnan(evaluate("symptoms", prepared, np.array([[0, 0, 3]]))[0, 0])
        )

    def test_batch_partition_does_not_change_logical_draws(self):
        config = dict(master_seed=47, expected_people=3)
        prepared = dict(
            numerator=np.array([[1, 0, 1]]), denominator=np.ones((1, 3), int)
        )
        a = execute_batch(config, prepared, "symptoms", 0, 10)
        b = execute_batch(config, prepared, "symptoms", 0, 4)
        c = execute_batch(config, prepared, "symptoms", 4, 10)

        def values(r):
            with np.load(io.BytesIO(r["blob"])) as f:
                return f["values"]

        self.assertTrue(
            np.array_equal(values(a), np.vstack([values(b), values(c)]), equal_nan=True)
        )


if __name__ == "__main__":
    unittest.main()
