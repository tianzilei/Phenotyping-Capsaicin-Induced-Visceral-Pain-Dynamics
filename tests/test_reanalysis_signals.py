import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
from capsaicin.reanalysis_signals import (
    derivative_flags,
    egg_spectrum,
    hb_mean,
    hb_means_matrix,
)


class Signals(unittest.TestCase):
    def test_linear_hb_preserved(self):
        t = np.arange(0, 600, 0.1)
        x = 0.2 * t
        flags = derivative_flags(x, 10)
        # floating precision of a linear slope must not turn it into an artifact
        self.assertLess(flags.mean(), 0.1)

    def test_spectral_units_and_gaps(self):
        t = np.arange(3000) / 10
        x = np.sin(2 * np.pi * 0.1 * t)
        r = egg_spectrum(x, np.zeros(len(x), bool), 10)
        self.assertAlmostEqual(r["peak_cpm"], 6, delta=0.47)
        bad = np.ones(len(x), bool)
        bad[:1200] = False
        bad[1500:] = False
        self.assertLess(egg_spectrum(x, bad, 10)["segments"], 2)

    def test_all_nan_hb(self):
        r = hb_mean(np.arange(10), np.full(10, np.nan), np.zeros(10, bool), 0, 9)
        self.assertIsNone(r["mean"])
        self.assertEqual(r["coverage"], 0)

    def test_matrix_matches_scalar(self):
        rng = np.random.default_rng(1)
        t = np.r_[np.arange(30), np.arange(40, 100)]
        x = rng.normal(size=(len(t), 3, 3))
        bad = rng.random((len(t), 3, 2)) < 0.1
        x[4, 0, 0] = np.nan
        means, coverage, _ = hb_means_matrix(t, x, bad, 1, 80)
        for j in range(3):
            for k in range(2):
                scalar = hb_mean(t, x[:, j, k], bad[:, j, k], 1, 80)
                self.assertAlmostEqual(means[j, k], scalar["mean"])
                self.assertAlmostEqual(coverage[j, k], scalar["coverage"])


if __name__ == "__main__":
    unittest.main()
