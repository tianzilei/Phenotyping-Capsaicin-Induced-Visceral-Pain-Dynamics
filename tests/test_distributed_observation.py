"""Synthetic ingestion, paired resampling, and exact MC rank boundaries."""

import unittest
import numpy as np
from scipy.stats import binom

from capsaicin.distributed_observation import (
    tokens_to_arrays,
    observation_statistics,
    prediction_statistics,
    index_stream,
    rank_interval,
    summarize_column,
)


class DistributedObservationTests(unittest.TestCase):
    def test_markers_missing_and_actual_grid_preserved(self):
        a = ["1", "", "3", "E"] + [""] * 16
        b = ["0", "2", "T"] + [""] * 17
        values, events = tokens_to_arrays([a, b])
        self.assertTrue(np.isnan(values[0, 1]))
        self.assertTrue(np.isnan(values[0, 3]))
        self.assertEqual(values[1, 0], 0)
        self.assertEqual(events.tolist(), [[4, 21], [21, 3]])
        result = observation_statistics(values, events, np.array([2, 1]))
        self.assertAlmostEqual(result[0], 2 / 3)
        self.assertEqual(result[1], 2)
        self.assertTrue(np.isnan(result[3]))
        self.assertAlmostEqual(result[20 + 2], 2 / 3)
        self.assertAlmostEqual(result[40 + 3], 2 / 3)
        self.assertAlmostEqual(result[60 + 2], 1 / 3)

    def test_invalid_tokens_and_post_stop_values_rejected(self):
        for row in (
            ["E", "1"] + [""] * 18,
            ["T", "E"] + [""] * 18,
            ["nan"] + [""] * 19,
            ["unknown"] + [""] * 19,
            ["11"] + [""] * 19,
        ):
            with self.assertRaises(ValueError):
                tokens_to_arrays([row])

    def test_person_multiplicity_equals_expanded_rows_and_paired_differences(self):
        counts = np.array([2, 1])
        a = np.array([[2.0, 4.0, 1.0], [3.0, 1.0, 2.0]])
        q = np.array([[2.0, 8.0, 0.5], [9.0, 1.0, 4.0]])
        weights = np.array([2, 1])
        result = prediction_statistics((counts, a, q), weights)
        selected = np.array([0, 0, 1])
        explicit = prediction_statistics(
            (counts[selected], a[selected], q[selected]), np.ones(3)
        )
        self.assertTrue(np.allclose(result, explicit))
        self.assertAlmostEqual(result[6], result[1] - result[0])
        self.assertAlmostEqual(result[8], result[4] - result[3])
        person_equal = prediction_statistics((counts, a, q), weights, True)
        self.assertFalse(np.allclose(result, person_equal))

    def test_subject_indices_independent_of_batch_order(self):
        a, h = index_stream(2026, "next_rating", 17, 40)
        index_stream(2026, "next_rating", 18, 40)
        b, j = index_stream(2026, "next_rating", 17, 40)
        self.assertEqual(h, j)
        self.assertTrue(np.array_equal(a, b))
        self.assertEqual(a.sum(), 40)
        self.assertNotEqual(h, index_stream(2026, "five_to_ten", 17, 40)[1])

    def test_exact_binomial_rank_definition_and_sentinels(self):
        for n in (1, 5, 20, 100):
            for p in (0.025, 0.5, 0.975):
                r, s = rank_interval(n, p, 0.05)
                self.assertLessEqual(binom.cdf(r - 1, n, p), 0.025)
                self.assertLessEqual(binom.sf(s - 1, n, p), 0.025)
                if r < n:
                    self.assertGreater(binom.cdf(r, n, p), 0.025)
                if s > 1:
                    self.assertGreater(binom.sf(s - 2, n, p), 0.025)
        self.assertEqual(rank_interval(1, 0.025, 0.05)[0], 0)
        self.assertEqual(rank_interval(1, 0.975, 0.05)[1], 2)

    def test_ties_zero_width_and_finite_MC_budget(self):
        cfg = dict(MC_total_error_probability=0.05, statistic_family_size=110)
        r = summarize_column(np.zeros(20000), cfg, [0, 1], "proportion")
        self.assertTrue(r["zero_width"])
        self.assertEqual(r["status"], "MC_PRECISION_MET")
        r = summarize_column(np.array([np.nan] * 5), cfg, [0, 10], "VAS")
        self.assertEqual(r["status"], "UNDEFINED_SUPPORT")
        r = summarize_column(np.array([1.0, 2.0, 3.0]), cfg, [None, None], "VAS")
        self.assertEqual(r["status"], "MC_PRECISION_INSUFFICIENT")


if __name__ == "__main__":
    unittest.main()
