"""Synthetic checks for unit-free advisory features."""

import unittest

import numpy as np

from capsaicin.egg_unitless_probes import unitless_egg_probes


class EggUnitlessProbeTests(unittest.TestCase):
    def signals(self, scale=1.0, drift=False, repeat=False):
        fs = 100
        t = np.arange(300 * fs) / fs
        ecg = 0.02 * np.sin(2 * np.pi * 1.2 * t)
        ecg[(np.arange(1, 299 / 1.2) * fs / 1.2).astype(int)] += 2
        egg = (
            np.stack(
                [np.sin(2 * np.pi * 0.05 * t), 0.8 * np.sin(2 * np.pi * 0.05 * t + 0.2)]
            )
            * scale
        )
        if drift:
            egg += scale * 4 * np.sin(2 * np.pi * 0.01 * t)
        if repeat:
            egg[:, 10000:10500] = egg[:, 10000:10001]
        return egg, ecg, fs

    def test_global_scale_does_not_change_dimensionless_features(self):
        x, ecg, fs = self.signals(1)
        a = unitless_egg_probes(x, ecg, fs)
        x2, ecg2, _ = self.signals(7)
        b = unitless_egg_probes(x2, ecg2, fs)
        self.assertAlmostEqual(
            a["subslow_ratio_max"], b["subslow_ratio_max"], places=10
        )
        self.assertAlmostEqual(
            a["modal_difference_fraction_max"],
            b["modal_difference_fraction_max"],
            places=10,
        )

    def test_smooth_drift_increases_subslow_ratio(self):
        clean, ecg, fs = self.signals()
        drift, _, _ = self.signals(drift=True)
        self.assertGreater(
            unitless_egg_probes(drift, ecg, fs)["subslow_ratio_max"],
            unitless_egg_probes(clean, ecg, fs)["subslow_ratio_max"],
        )

    def test_repeated_run_increases_repeat_features(self):
        clean, ecg, fs = self.signals()
        repeated, _, _ = self.signals(repeat=True)
        a = unitless_egg_probes(clean, ecg, fs)
        b = unitless_egg_probes(repeated, ecg, fs)
        self.assertGreater(
            b["exact_repeat_fraction_max"], a["exact_repeat_fraction_max"]
        )
        self.assertFalse(b["harmonic_probe_in_egg_analysis_band"])
        self.assertIn("not_dropout_evidence", b["repeat_probe_interpretation"])
        self.assertEqual(
            b["semantic_status"],
            "unitless_advisory_probe_not_artifact_or_crosstalk_acceptance",
        )


if __name__ == "__main__":
    unittest.main()
