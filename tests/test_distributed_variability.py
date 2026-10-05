"""Synthetic gap, integration, residual and joint whole-person resampling checks."""

import json
from pathlib import Path
import unittest
import numpy as np
from capsaicin.distributed_variability import (
    residual_metrics,
    burden_metrics,
    prepare_matrix,
    specifications,
    weighted_statistics,
    bootstrap_batch,
)


class DistributedVariabilityTests(unittest.TestCase):
    def config(self):
        cfg = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "config/dask_variability_bootstrap_20261003_v1.json"
            ).read_text()
        )
        cfg["prepared_input_sha256"] = {"U06_variability": "synthetic_only"}
        return cfg

    def test_exact_piecewise_linear_burden_and_zero_area(self):
        # y=t on [1,5]: area12, first moment124/3, late area8.
        area, centroid, fraction = burden_metrics(np.arange(1, 6), np.arange(1, 6))
        self.assertAlmostEqual(area, 12)
        self.assertAlmostEqual(centroid, (124 / 3) / 12)
        self.assertAlmostEqual(fraction, 8 / 12)
        area, centroid, fraction = burden_metrics([1, 2, 3], [0, 0, 0])
        self.assertEqual(area, 0)
        self.assertTrue(np.isnan(centroid))
        self.assertTrue(np.isnan(fraction))
        with self.assertRaises(ValueError):
            burden_metrics([1, 3], [1, 3])

    def test_residual_degrees_of_freedom_and_actual_adjacency(self):
        t = np.array([1, 2, 3, 5, 6, 7])
        y = np.array([1, 3, 2, 5, 4, 6.0])
        x = np.c_[np.ones(6), t - t.mean()]
        e = y - x @ np.linalg.lstsq(x, y, rcond=None)[0]
        variance, mssd, raw = residual_metrics(t, y, 1)
        self.assertAlmostEqual(variance, (e @ e) / 4)
        self.assertAlmostEqual(mssd, np.mean(np.diff(e)[np.diff(t) == 1] ** 2))
        self.assertAlmostEqual(raw, np.mean([4, 1, 1, 4]))
        with self.assertRaises(ValueError):
            residual_metrics([1, 1, 2], [1, 2, 3], 1)

    def test_person_multiplicity_median_even_odd_mean_and_undefined(self):
        matrix = np.array(
            [[1.0, 10.0, np.nan], [3.0, 20.0, np.nan], [9.0, np.nan, np.nan]]
        )
        specs = [
            dict(aggregation="median"),
            dict(aggregation="mean"),
            dict(aggregation="median"),
        ]
        for weights in (np.array([1, 1, 0]), np.array([1, 1, 1]), np.array([2, 1, 1])):
            actual, count = weighted_statistics(matrix, weights, specs)
            expanded = np.repeat(matrix, weights, axis=0)
            self.assertEqual(actual[0], np.median(expanded[:, 0]))
            self.assertEqual(actual[1], np.nanmean(expanded[:, 1]))
            self.assertTrue(np.isnan(actual[2]))
            self.assertEqual(count[2], 0)
        with self.assertRaises(ValueError):
            weighted_statistics(matrix, [0.5, 1, 1], specs)

    def test_gap_support_complete_burden_and_paired_support(self):
        cfg = self.config()
        values = np.vstack([np.ones(20) * 2, np.ones(20) * 4])
        values[1, 2] = np.nan
        m = prepare_matrix(values, cfg)
        names = [x["statistic"] for x in specifications(cfg)]
        self.assertEqual(m.shape, (2, 96))
        self.assertTrue(np.isnan(m[1, names.index("raw_1_5_at_least_3_pairs_mssd")]))
        self.assertTrue(np.isnan(m[1, names.index("burden_1_20_auc")]))
        self.assertTrue(np.isnan(m[1, names.index("paired_16_20_minus_1_5_mean_vas")]))
        self.assertEqual(m[0, names.index("burden_1_20_auc")], 38)
        self.assertEqual(m[0, names.index("raw_1_5_at_least_3_pairs_mssd")], 0)

    def test_no_support_is_preserved_not_replaced(self):
        cfg = self.config()
        matrix = np.full((3, 96), np.nan)
        batch = bootstrap_batch(cfg, (matrix,), "U06_variability", 0, 3)
        self.assertEqual(batch["payload"]["statistics"], [[None] * 96] * 3)
        self.assertEqual(batch["payload"]["resampled_support_max"], [0] * 96)

    def test_reordered_batch_rng_and_numeric_results(self):
        cfg = self.config()
        values = np.vstack([np.arange(20) / 2, np.ones(20) * 2, np.ones(20) * 4])
        matrix = prepare_matrix(values, cfg)
        full = bootstrap_batch(cfg, (matrix,), "U06_variability", 0, 10)["payload"]
        a = bootstrap_batch(cfg, (matrix,), "U06_variability", 5, 10)["payload"]
        b = bootstrap_batch(cfg, (matrix,), "U06_variability", 0, 5)["payload"]
        self.assertEqual(full["statistics"], b["statistics"] + a["statistics"])
        self.assertEqual(full["index_sha256"], b["index_sha256"] + a["index_sha256"])


if __name__ == "__main__":
    unittest.main()
