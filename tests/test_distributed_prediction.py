"""Synthetic target support and train-only subject split tests."""

import json
from pathlib import Path
import unittest
import numpy as np
from capsaicin.distributed_prediction import (
    prepare_arrays,
    fold_indices,
    execute_fold,
    repeat_summary,
    seed,
)


class DistributedPredictionTests(unittest.TestCase):
    def config(self):
        cfg = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "config/dask_prediction_repeats_20261003_v1.json"
            ).read_text()
        )
        cfg.update(
            forest_trees=3,
            ridge_alpha=[1],
            forest_depth=[2],
            prepared_input_sha256={
                "next_rating": "synthetic",
                "five_to_ten": "synthetic",
            },
        )
        return cfg

    def test_future_targets_do_not_bridge_gaps_or_impute_tails(self):
        values = np.vstack([np.arange(20) / 2, np.arange(20) / 2])
        values[1, 3] = np.nan
        values[1, 10:] = np.nan
        x, y, g, t = prepare_arrays(values, "next_rating")
        self.assertEqual(len(y), 20)
        self.assertEqual(t[g == 1].tolist(), [7, 8, 9])
        self.assertEqual(x[g == 1, 3].tolist(), [7, 8, 9])
        self.assertTrue(np.all(y[g == 1] == np.array([3.5, 4, 4.5])))
        x, y, g, t = prepare_arrays(values, "five_to_ten")
        self.assertEqual(g.tolist(), [0])
        self.assertEqual(y.tolist(), [4.5])

    def test_both_cv_levels_keep_whole_people_disjoint(self):
        cfg = self.config()
        v = np.tile(np.arange(20) / 2, (30, 1))
        prepared = prepare_arrays(v, "next_rating")
        _, _, groups, _ = prepared
        tests = []
        for fold in range(5):
            train, test, inner = fold_indices(cfg, prepared, "next_rating", 0, fold)
            tests.extend(test.tolist())
            self.assertFalse(set(groups[train]) & set(groups[test]))
            for a, b in inner:
                self.assertFalse(set(groups[train[a]]) & set(groups[train[b]]))
        self.assertEqual(sorted(tests), list(range(len(groups))))
        self.assertNotEqual(
            seed(cfg, "next_rating", 0, "outer"), seed(cfg, "next_rating", 1, "outer")
        )
        self.assertNotEqual(
            seed(cfg, "next_rating", 0, "outer"), seed(cfg, "five_to_ten", 0, "outer")
        )

    def test_pipeline_and_oof_reconstruction_with_duplicate_rejection(self):
        cfg = self.config()
        v = np.random.default_rng(91).uniform(0, 10, (20, 20))
        prepared = prepare_arrays(v, "five_to_ten")
        payloads = [
            execute_fold(cfg, prepared, "five_to_ten", 0, fold)["payload"]
            for fold in range(5)
        ]
        summary = repeat_summary(payloads, prepared, cfg)
        expected = float(np.mean(abs(v[:, 4] - v[:, 9])))
        self.assertAlmostEqual(summary["person_equal"]["MAE_last_value"], expected)
        self.assertAlmostEqual(
            summary["person_equal"]["MAE_ridge_minus_last_value"],
            summary["person_equal"]["MAE_ridge"] - expected,
        )
        with self.assertRaises(ValueError):
            repeat_summary(payloads + [payloads[0]], prepared, cfg)
        repeat = execute_fold(cfg, prepared, "five_to_ten", 0, 0)["payload"]
        self.assertEqual(repeat, payloads[0])


if __name__ == "__main__":
    unittest.main()
