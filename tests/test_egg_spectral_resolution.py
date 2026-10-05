"""Synthetic physical-width checks; these values are not confidence intervals."""

import unittest

from capsaicin.egg_spectral_resolution import bandwidth_metadata


class EggSpectralResolutionTests(unittest.TestCase):
    def test_short_and_long_runs_have_correct_bandwidth(self):
        short = bandwidth_metadata(6 / 120)
        self.assertAlmostEqual(short["dpss_half_bandwidth_cpm"], 1.5)
        self.assertEqual(
            short["resolution_annotation"], "UNDER_300S_RESOLUTION_CAUTION"
        )
        standard = bandwidth_metadata(6 / 300)
        self.assertAlmostEqual(standard["dpss_half_bandwidth_cpm"], 0.6)
        self.assertEqual(
            standard["resolution_annotation"], "RESOLUTION_METADATA_RECORDED"
        )
        self.assertFalse(standard["bandwidth_is_confidence_interval"])

    def test_nonpositive_width_is_rejected(self):
        with self.assertRaises(ValueError):
            bandwidth_metadata(0)


if __name__ == "__main__":
    unittest.main()
