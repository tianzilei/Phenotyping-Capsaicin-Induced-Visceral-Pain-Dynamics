import unittest
import numpy as np
from capsaicin.egg_stability import fixed_segment, spectrum_distance


class EggStabilityTests(unittest.TestCase):
    def test_equal_spectra_have_zero_distance(self):
        t = np.arange(1200) / 10
        x = np.stack([np.sin(2 * np.pi * 0.05 * t), np.sin(2 * np.pi * 0.05 * t)])
        corr, dist = spectrum_distance(x, x, 10)
        self.assertAlmostEqual(corr, 1)
        self.assertAlmostEqual(dist, 0)

    def test_fixed_segment_does_not_pad(self):
        x = np.zeros((2, 1000))
        self.assertEqual(fixed_segment(x, 10, 20, 30, 10).shape, (2, 300))
        with self.assertRaises(ValueError):
            fixed_segment(x, 10, 80, 30, 10)


if __name__ == "__main__":
    unittest.main()
