import unittest
import numpy as np
from capsaicin.egg_peaks import peak_descriptors, variant_spectrum


class EggPeakTests(unittest.TestCase):
    def test_monotone_psd_has_no_interior_peak(self):
        f = np.arange(257) / 128
        p = 1 / (f + 0.001)
        r, peaks = peak_descriptors(f, p)
        self.assertTrue(r["boundary_maximum"])
        self.assertEqual(peaks, [])
        self.assertIsNone(r["strongest_local_hz"])
        self.assertAlmostEqual(
            sum(r[k + "_fraction"] for k in ["low", "middle", "high"]), 1
        )

    def test_peak_is_distinct_from_boundary(self):
        f = np.arange(257) / 128
        p = np.ones(len(f))
        p[2] = 10
        p[7] = 5
        r, peaks = peak_descriptors(f, p)
        self.assertTrue(r["boundary_maximum"])
        self.assertEqual(r["strongest_local_hz"], 7 / 128)
        self.assertEqual(r["strongest_local_to_max"], 0.5)

    def test_known_sine_across_segment_lengths(self):
        t = np.arange(1120) / 4
        y = np.sin(2 * np.pi * 0.05 * t)
        for seconds in [128, 256]:
            r, _, _ = variant_spectrum(
                y,
                4,
                dict(name="test", segment_seconds=seconds, window_polynomial_degree=0),
            )
            self.assertFalse(r["boundary_maximum"])
            self.assertLess(abs(r["maximum_hz"] - 0.05), 1 / seconds)

    def test_missing_or_negative_psd_rejected(self):
        f = np.arange(257) / 128
        with self.assertRaises(ValueError):
            peak_descriptors(f, -np.ones(len(f)))
        p = np.ones(len(f))
        p[0] = np.nan
        with self.assertRaises(ValueError):
            peak_descriptors(f, p)
        self.assertEqual(
            peak_descriptors(f, np.zeros(len(f)))[0]["status"], "zero_band_power"
        )
