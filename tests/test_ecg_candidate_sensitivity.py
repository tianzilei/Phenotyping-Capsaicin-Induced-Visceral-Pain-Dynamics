import json
from pathlib import Path
import unittest
import numpy as np
from capsaicin.ecg_candidates import (
    detect_candidates,
    detect_candidates_from_filtered,
    synthetic_ecg,
    enforce_distance,
)


class ECGCandidateSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(
            (
                Path(__file__).resolve().parents[1] / "config/ecg_candidates_v1.json"
            ).read_text()
        )

    def test_filtered_path_matches_full_path(self):
        y, _ = synthetic_ecg("motion_burst", np.random.default_rng(9), 60)
        full = detect_candidates(y, 250, self.cfg)
        filt = detect_candidates_from_filtered(full["filtered"], 250, self.cfg)
        np.testing.assert_array_equal(full["amplitude"], filt["amplitude"])
        np.testing.assert_array_equal(full["energy"], filt["energy"])

    def test_subset_before_refractory_can_increase_final_count(self):
        scores = np.zeros(12)
        scores[[2, 5, 8]] = [1, 3, 2]
        self.assertEqual(enforce_distance([2, 5, 8], scores, 4).tolist(), [5])
        self.assertEqual(enforce_distance([2, 8], scores, 4).tolist(), [2, 8])

    def test_zero_mad_remains_finite(self):
        y = np.zeros(15000)
        y[5000] = 1
        cfg = dict(
            self.cfg,
            amplitude_prominence_mad_multiplier=5,
            energy_threshold_mad_multiplier=5,
        )
        found = detect_candidates(y, 250, cfg)
        self.assertTrue(np.isfinite(found["filtered"]).all())
