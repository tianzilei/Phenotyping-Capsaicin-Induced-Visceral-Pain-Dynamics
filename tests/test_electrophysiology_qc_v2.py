"""Synthetic regression tests for the development-only diagnostics."""

import unittest

import numpy as np

from capsaicin.electrophysiology_qc_v2 import (
    align_candidate,
    coincidence_diagnostic,
    continuous_runs,
    egg_candidate,
    event_clusters,
    multitaper_run,
    raw_egg_mask,
)


class DevelopmentQCTests(unittest.TestCase):
    def test_qrs_alignment_uses_bounded_lead_ii_extremum(self):
        lead = np.zeros(200)
        lead[104] = -3
        lead[130] = 7
        self.assertEqual(align_candidate(100, lead, fs=100, radius_seconds=0.08), 104)
        self.assertEqual(align_candidate(0, lead, fs=100), 0)

    def test_event_cluster_counts_distinct_leads_and_does_not_chain(self):
        groups = event_clusters(
            [[100, 101, 170], [102, 175], [106, 190]], fs=1000, tolerance_seconds=0.005
        )
        self.assertEqual(groups[0][1], 2)
        self.assertEqual(groups[1][1], 1)
        self.assertEqual(groups[2][1], 2)

    def test_shift_null_is_reproducible_and_does_not_wrap(self):
        peaks = [np.arange(100, 1900, 100), np.arange(101, 1900, 100)]
        first = coincidence_diagnostic(peaks, fs=100, n_samples=2000, seed=11)
        self.assertEqual(first, coincidence_diagnostic(peaks, 100, 2000, seed=11))
        self.assertEqual(first["coincidence_core_seconds"], 10)
        self.assertGreaterEqual(
            first["shift_coincidence_rate_max_per_minute"],
            first["shift_coincidence_rate_median_per_minute"],
        )
        self.assertIn("not_false_positive", first["shift_semantics"])

    def test_shift_null_rejects_too_short_common_core(self):
        self.assertIsNone(coincidence_diagnostic([[1], [2]], fs=10, n_samples=30))

    def test_mask_keeps_last_sample_and_splits_nonfinite_gap(self):
        x = np.tile(np.sin(np.arange(1000) * 0.03), (2, 1))
        x[0, 200:220] = np.nan
        mask, counts = raw_egg_mask(x, fs=10)
        self.assertEqual(counts["nonfinite_samples"], 20)
        self.assertEqual(continuous_runs(mask), [(0, 200), (220, 1000)])

    def test_exact_long_flatline_is_invalid(self):
        x = np.tile(np.sin(np.arange(1000) * 0.03), (2, 1))
        x[0, 300:330] = 1.0
        mask, counts = raw_egg_mask(x, fs=10, flat_seconds=2)
        self.assertGreaterEqual(counts["flatline_samples"], 29)
        self.assertFalse(mask[310])

    def test_gap_is_never_bridged_to_satisfy_minimum_run(self):
        fs = 10
        t = np.arange(220 * fs) / fs
        x = np.tile(np.sin(2 * np.pi * 0.05 * t), (2, 1))
        x[:, 1000:1100] = np.nan
        result = egg_candidate(
            x, fs, minimum_run_seconds=120, minimum_total_seconds=180, target_fs=10
        )
        self.assertEqual(result["valid_run_count"], 0)
        self.assertEqual(result["status"], "EGG_CANDIDATE_INESTIMABLE")

    def test_unequal_runs_have_finite_descriptive_spectrum(self):
        fs = 10
        t = np.arange(310 * fs) / fs
        x = np.tile(np.sin(2 * np.pi * 0.05 * t), (2, 1))
        x[:, 1300:1320] = np.nan
        result = egg_candidate(
            x, fs, minimum_run_seconds=120, minimum_total_seconds=180, target_fs=10
        )
        self.assertEqual(result["valid_run_count"], 2)
        self.assertEqual(result["status"], "EGG_CANDIDATE_SPECTRUM_ONLY")
        self.assertTrue(np.isfinite(result["slow_power_ratio"]))
        self.assertLess(abs(result["peak_cpm_weighted"] - 3.0), 0.5)

    def test_taper_coherence_is_not_single_periodogram_identity(self):
        rng = np.random.default_rng(14)
        _, _, coherence = multitaper_run(rng.normal(size=(2, 3000)), fs=10)
        self.assertLess(float(np.median(coherence[1:])), 0.6)


if __name__ == "__main__":
    unittest.main()
