import unittest
import numpy as np
from capsaicin.derivative_v5 import basis, fit_derivative


class DerivativeV5Tests(unittest.TestCase):
    def test_partition_and_analytic_quadratic(self):
        grid = np.arange(1.0, 21.0)
        x, d = basis(grid, (1, 20), 10)
        self.assertTrue(np.allclose(x.sum(axis=1), 1))
        self.assertTrue(np.allclose(d.sum(axis=1), 0))
        beta = np.linalg.lstsq(x, 2 + 0.5 * grid - 0.02 * grid**2, rcond=None)[0]
        self.assertTrue(np.allclose(d @ beta, 0.5 - 0.04 * grid, atol=1e-10))

    def test_duplicate_and_missing_support_rejected(self):
        ids = np.repeat(np.arange(20), 20)
        times = np.tile(np.arange(1, 21), 20)
        vals = np.ones(len(ids))
        with self.assertRaises(ValueError):
            fit_derivative(ids, np.ones(len(ids)), vals, (1, 20))
        keep = times < 20
        with self.assertRaises(ValueError):
            fit_derivative(ids[keep], times[keep], vals[keep], (1, 20))

    def test_subject_jackknife_known_linear_slope(self):
        grid = np.arange(1.0, 21.0)
        slopes = np.linspace(0.1, 0.3, 20)
        values = (3 + slopes[:, None] * grid).ravel()
        r = fit_derivative(
            np.repeat(np.arange(20), 20), np.tile(grid, 20), values, (1, 20)
        )
        self.assertTrue(np.allclose(r["estimate"], slopes.mean(), atol=1e-9))
        self.assertTrue(
            np.allclose(r["se"], np.std(slopes, ddof=1) / np.sqrt(20), atol=1e-9)
        )

    def test_subject_permutation_invariant(self):
        rng = np.random.default_rng(712)
        ids = np.repeat(np.arange(20), 20)
        times = np.tile(np.arange(1, 21), 20)
        vals = 3 + 0.1 * times + rng.normal(size=len(times))
        a = fit_derivative(ids, times, vals, (1, 20))
        p = rng.permutation(len(times))
        b = fit_derivative(ids[p], times[p], vals[p], (1, 20))
        self.assertTrue(np.allclose(a["estimate"], b["estimate"]))
        self.assertTrue(np.allclose(a["se"], b["se"]))
