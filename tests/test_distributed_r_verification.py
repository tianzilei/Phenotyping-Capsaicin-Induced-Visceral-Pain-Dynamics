"""Synthetic edge cases for the independent, read-only R result verifier."""

import sys
from pathlib import Path
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from verify_dask_R_analysis import (
    enumerated_ranks,
    independently_summarize,
    verify_reconstruction_numerics,
    portable_reconstruction_checker,
)
from capsaicin.distributed_observation import rank_interval


class VerificationTests(unittest.TestCase):
    def test_independent_ranks_include_sentinels(self):
        self.assertEqual(enumerated_ranks(1, 0.025, 0.001), (0, 2))
        for n in [1, 7, 100, 5000]:
            for p in [0.025, 0.5, 0.975]:
                for gamma in [0.05, 0.05 / 240]:
                    self.assertEqual(
                        enumerated_ranks(n, p, gamma), rank_interval(n, p, gamma)
                    )

    def test_ties_and_undefined_sentinel_are_retained(self):
        result = independently_summarize([3.0] * 5000, 0.05 / 240, [None, None])
        self.assertEqual(result["empirical_range_width"], 0)
        self.assertEqual(result["MC_max_endpoint_half_width"], 0)
        weak = independently_summarize([3.0], 0.001, [None, None])
        self.assertIsNone(weak["MC_max_endpoint_half_width"])
        self.assertIsNone(weak["lower"]["lower_MC"])
        bounded = independently_summarize([0.5], 0.001, [0, 1])
        self.assertEqual(bounded["MC_max_endpoint_half_width"], 0.5)

    def test_nonfinite_success_is_rejected(self):
        for values in [[], [np.nan], [1, np.inf]]:
            with self.assertRaises(ValueError):
                independently_summarize(values, 0.05, [None, None])

    @staticmethod
    def reconstruction_fixture():
        offsets = np.arange(10.0) * 0.5
        curve = np.array([0.0, 1.0, 2.0, 1.0])
        y = offsets[:, None] + curve
        tr = list(range(6))
        te = list(range(6, 10))
        weights = np.array([0.5, 1.0, 1.0, 0.5])
        mean = curve + 1.25
        constant = curve @ weights / weights.sum()
        baseline = float(np.sqrt((curve - constant) ** 2 @ weights / weights.sum()))
        errors = np.zeros((4, 5))
        errors[:, 0] = offsets[te] - 1.25
        request = dict(data=dict(y=y.tolist()), train=tr, test=te)
        saved = dict(
            train_rows=tr,
            test_rows=te,
            training_mean=mean.tolist(),
            person_constant_rmse=[baseline] * 4,
            rmse_k0_to_4=errors.tolist(),
            paired_loss_difference=(errors - baseline).tolist(),
        )
        return request, saved

    def test_analytic_rank_one_reconstruction(self):
        request, saved = self.reconstruction_fixture()
        result = verify_reconstruction_numerics([(request, saved)])
        self.assertEqual(result["status"], "PASS")
        self.assertLess(max(result["max_absolute_difference"].values()), 1e-12)

    def test_portable_checker_serialization(self):
        from distributed.protocol.pickle import dumps, loads

        request, saved = self.reconstruction_fixture()
        checker = loads(dumps(portable_reconstruction_checker()))
        self.assertEqual(checker([(request, saved)])["status"], "PASS")

    def test_leakage_and_wrong_saved_baseline_rejected(self):
        request, saved = self.reconstruction_fixture()
        request["test"][0] = request["train"][0]
        with self.assertRaises(ValueError):
            verify_reconstruction_numerics([(request, saved)])
        request, saved = self.reconstruction_fixture()
        saved["person_constant_rmse"][0] += 1
        with self.assertRaises(ValueError):
            verify_reconstruction_numerics([(request, saved)])


if __name__ == "__main__":
    unittest.main()
