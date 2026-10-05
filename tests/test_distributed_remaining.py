"""Synthetic partition alignment, repeated training, and FE multiplicity checks."""

import json
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from capsaicin.distributed_remaining import (
    partition_metrics,
    classifier_metrics,
    training_fold,
    old_candidate_fit,
    candidate_batch,
)
from capsaicin.completion import fe_sufficient, solve_fe


class RemainingTests(unittest.TestCase):
    def config(self):
        return json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "config/dask_python_remaining_20261003_v1.json"
            ).read_text()
        )

    def test_unsupervised_permutation_and_oob_minimum(self):
        ref = np.array([0, 0, 1, 1])
        pred = 1 - ref
        stats, flags = partition_metrics(ref, pred, np.array([0, 2]), 2)
        self.assertEqual(stats[:3], [1, 1, 1])
        self.assertFalse(flags["collapsed_fit"])
        stats, flags = partition_metrics(ref, pred, np.array([0]), 2)
        self.assertTrue(np.isnan(stats[1]))
        self.assertEqual(flags["oob_people"], 1)
        # Classifier scores never optimize a permutation of test predictions.
        self.assertEqual(classifier_metrics(ref, pred, 2), [0, 0, 0])

    def test_fuzzy_entropy_and_declared_missing_class_policy(self):
        u = np.full((4, 2), 0.5)
        s, f = partition_metrics(
            np.array([0, 0, 1, 1]), np.array([0, 0, 1, 1]), np.array([0, 2]), 2, u
        )
        self.assertAlmostEqual(s[3], np.log(2))
        self.assertAlmostEqual(s[4], np.log(2))
        self.assertEqual(classifier_metrics([0, 0], [0, 0], 3), [1, 1, 1 / 3])

    def test_training_shapelets_only_and_seed_repeat_changes_split(self):
        cfg = self.config()
        cfg["recovery"]["maximum_candidates_per_training_class"] = 5
        x = np.random.default_rng(42).uniform(0, 10, (40, 10))
        cell = dict(id="r10k2", k=2, interval_key="10")
        job = dict(stage="recovery", cell=cell, repeat=0, fold=0)
        r = training_fold(cfg, dict(x=x), job)
        self.assertFalse(set(r["train_rows"]) & set(r["test_rows"]))
        for origin in r["shapelet_origins"]:
            self.assertIn(origin["source_row"], r["train_rows"])
            self.assertNotIn(origin["source_row"], r["test_rows"])
            self.assertLessEqual(origin["start_index"] + 5, origin["prefix"])
        r2 = training_fold(cfg, dict(x=x), dict(job, repeat=1))
        self.assertNotEqual(r["test_rows"], r2["test_rows"])

    def test_fixed_effect_multiplicity_matches_explicit_relabelled_copies(self):
        rng = np.random.default_rng(9)
        g = np.repeat(np.arange(8), 4)
        block = np.tile(np.arange(4), 8)
        x = rng.normal(size=32)
        y = 3 * x + g + 0.2 * block + rng.normal(0, 0.1, 32)
        d = pd.DataFrame(dict(person_id=g, block=block, x=x, y=y))
        p = fe_sufficient(d, "y", ["x"])
        counts = np.array([2, 0, 1, 1, 3, 0, 1, 0])
        compressed = dict(gram=p["gram"], row_counts=np.full(8, 4))
        fit = old_candidate_fit(compressed, counts)
        copies = []
        for new, person in enumerate(np.repeat(np.arange(8), counts)):
            z = d[d.person_id == person].copy()
            z["person_id"] = new
            copies.append(z)
        expected = solve_fe(fe_sufficient(pd.concat(copies), "y", ["x"]))
        self.assertAlmostEqual(fit["coefficients"][0], expected["coefficients"][0])
        cfg = self.config()
        cell = dict(id="toy", kind="planned24", p=1)
        r = candidate_batch(cfg, compressed, dict(cell=cell, start=0, stop=10))
        self.assertEqual(len(r["statistics"]), 10)
        self.assertEqual(len(r["failures"]), 10)

    def test_inestimable_development_support_remains_null(self):
        cfg = self.config()
        cell = dict(id="b20k5", k=5, interval_key="20")
        r = training_fold(
            cfg,
            dict(x=np.ones((6, 20))),
            dict(stage="baseline", cell=cell, repeat=0, fold=0),
        )
        self.assertEqual(r["status"], "inestimable")
        self.assertEqual(r["metrics"], [])


if __name__ == "__main__":
    unittest.main()
