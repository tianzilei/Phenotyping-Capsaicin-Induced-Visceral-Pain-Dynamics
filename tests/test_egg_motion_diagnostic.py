"""Synthetic edge cases for the EGG motion-support sensitivity diagnostic."""

import unittest

import numpy as np

from capsaicin.egg_motion_diagnostic import motion_screened_spectrum, motion_support


class EggMotionDiagnosticTests(unittest.TestCase):
    @staticmethod
    def wave(seconds=300, fs=50):
        t = np.arange(int(seconds * fs)) / fs
        x = np.sin(2 * np.pi * 0.05 * t)
        return np.stack([x, 0.8 * x])

    def test_clean_slow_wave_keeps_long_support(self):
        x = self.wave()
        result, mask = motion_support(x, 50)
        self.assertEqual(result["support_status"], "MOTION_SCREENED_CANDIDATE_SUPPORT")
        self.assertGreater(result["qualifying_total_seconds"], 270)
        self.assertGreater(mask.mean(), 0.9)

    def test_step_and_spike_are_detected_without_unit_threshold(self):
        x = self.wave()
        x[0, 100 * 50 :] += 3
        x[1, 200 * 50] += 10
        result, mask = motion_support(x, 50)
        self.assertGreater(result["motion_candidate_seconds"], 0)
        self.assertFalse(mask[100 * 50])
        self.assertFalse(mask[200 * 50])
        spectral = motion_screened_spectrum(x, 50, mask, target_fs=10)
        self.assertEqual(
            spectral["motion_spectrum_status"], "MOTION_SCREENED_SPECTRUM_INESTIMABLE"
        )

    def test_long_clean_tail_recovers_candidate_frequency(self):
        x = self.wave(420)
        x[0, 100 * 50 :] += 3
        x[1, 200 * 50] += 10
        _, mask = motion_support(x, 50)
        spectral = motion_screened_spectrum(x, 50, mask, target_fs=10)
        self.assertEqual(
            spectral["motion_spectrum_status"],
            "MOTION_SCREENED_SPECTRUM_CANDIDATE_ONLY",
        )
        self.assertLess(abs(spectral["motion_spectrum_peak_cpm_weighted"] - 3), 0.5)

    def test_missing_interval_is_not_bridged(self):
        x = self.wave(220)
        x[:, 100 * 50 : 120 * 50] = np.nan
        result, mask = motion_support(x, 50)
        self.assertEqual(result["nonfinite_samples"], 1000)
        self.assertFalse(mask[110 * 50])
        self.assertEqual(
            result["support_status"], "MOTION_SCREENED_CANDIDATE_INESTIMABLE"
        )
        spectral = motion_screened_spectrum(x, 50, mask, target_fs=10)
        self.assertEqual(
            spectral["motion_spectrum_status"], "MOTION_SCREENED_SPECTRUM_INESTIMABLE"
        )

    def test_nonfinite_sample_cannot_be_marked_valid(self):
        x = self.wave()
        x[0, 10] = np.nan
        mask = np.ones(x.shape[1], dtype=bool)
        with self.assertRaises(ValueError):
            motion_screened_spectrum(x, 50, mask, target_fs=10)

    def test_flatline_is_invalid_even_without_derivative_flag(self):
        x = self.wave()
        x[1, 150 * 50 : 154 * 50] = 2
        result, mask = motion_support(x, 50)
        self.assertGreater(result["flatline_samples"], 0)
        self.assertFalse(mask[152 * 50])


if __name__ == "__main__":
    unittest.main()
