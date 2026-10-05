import json
import unittest
from pathlib import Path
import numpy as np
from capsaicin.signal_spectra import resample_exact, band_area, window_spectrum


class SignalSpectraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(
            (
                Path(__file__).resolve().parents[1] / "config/signal_spectra_v1.json"
            ).read_text()
        )

    def test_exact_fractional_resampling(self):
        x = np.ones(75000)
        y = resample_exact(x, 250, 4)
        self.assertEqual(len(y), 1200)
        np.testing.assert_allclose(y[40:-40], 1, atol=1e-5)

    def test_alias_rejection(self):
        t = np.arange(40000) / 2000
        # 249 Hz would alias to 1 Hz if simply selecting every eighth sample.
        x = np.sin(2 * np.pi * 249 * t)
        y = resample_exact(x, 2000, 250)[250:-250]
        self.assertLess(np.std(y), 0.001)
        self.assertGreater(np.std(x[::8]), 0.6)

    def test_band_integral_edges(self):
        f = np.arange(6.0)
        self.assertAlmostEqual(band_area(f, 2 * f, 0.4, 3.2), 3.2**2 - 0.4**2)

    def test_known_gastric_frequency(self):
        t = np.arange(600000) / 2000
        r, _ = window_spectrum(np.sin(2 * np.pi * 0.05 * t), "EGG100C", self.cfg)
        self.assertLess(abs(r["band_max_hz"] - 0.05), 1 / 128)
        self.assertGreater(r["norm_fraction"], 0.95)
        self.assertEqual(r["effective_rate_hz"], 4)
        self.assertEqual(r["welch_segments"], 3)

    def test_no_missing_fill_or_constant_ratio(self):
        x = np.zeros(600000)
        self.assertEqual(
            window_spectrum(x, "EGG100C", self.cfg)[0]["spectral_status"],
            "constant_raw_no_ratio",
        )
        x[100] = np.nan
        self.assertEqual(
            window_spectrum(x, "EGG100C", self.cfg)[0]["spectral_status"],
            "nonfinite_raw_no_fill",
        )
        with self.assertRaises(ValueError):
            resample_exact(x, 2000, 4)
        with self.assertRaises(ValueError):
            window_spectrum(x[:-1], "EGG100C", self.cfg)
