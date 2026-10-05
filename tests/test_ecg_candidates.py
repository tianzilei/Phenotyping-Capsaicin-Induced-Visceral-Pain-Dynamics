import json
from pathlib import Path
import unittest
import numpy as np
from capsaicin.ecg_candidates import (
    detect_candidates,
    detect_multilead,
    match_candidates,
    synthetic_ecg,
    enforce_distance,
)


class ECGCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(
            (
                Path(__file__).resolve().parents[1] / "config/ecg_candidates_v1.json"
            ).read_text()
        )

    def test_one_to_one_and_boundary(self):
        self.assertEqual(match_candidates([1, 1.02], [1.01], 0.05), [(0, 0)])
        self.assertEqual(match_candidates([1], [1.05], 0.05), [(0, 0)])
        self.assertEqual(match_candidates([], [], 0.05), [])
        with self.assertRaises(ValueError):
            match_candidates([2, 1], [1], 0.05)

    def test_flat_missing_and_short(self):
        r = detect_candidates(np.zeros(10000), 250, self.cfg)
        self.assertEqual(len(r["amplitude"]), 0)
        self.assertEqual(len(r["energy"]), 0)
        for x in (np.full(10000, np.nan), np.zeros(10)):
            with self.assertRaises(ValueError):
                detect_candidates(x, 250, self.cfg)

    def test_known_beats_inversion_and_origin(self):
        y, truth = synthetic_ecg("clean", np.random.default_rng(37), 60)
        valid = truth[(truth >= 10) & (truth < 50)]
        for sign in (1, -1):
            r = detect_candidates(y * sign, 250, self.cfg)
            for method in ("amplitude", "energy"):
                actual = (r[method] + r["offset_samples"]) / 250
                matched = match_candidates(actual, valid, 0.05)
                self.assertGreaterEqual(len(matched) / len(valid), 0.95)
                self.assertGreaterEqual(len(matched) / len(actual), 0.95)

    def test_refractory_across_threshold_blocks(self):
        scores = np.zeros(100)
        scores[[49, 51, 80]] = [1, 2, 3]
        self.assertEqual(enforce_distance([49, 51, 80], scores, 10).tolist(), [51, 80])

    def test_multilead_spatial_detector_preserves_candidate_only_contract(self):
        y, truth = synthetic_ecg("clean", np.random.default_rng(41), 60)
        leads = np.vstack([y, y * 0.9, -y * 1.1])
        cfg = json.loads(
            (
                Path(__file__).resolve().parents[1] / "config/ecg_multilead_v1.json"
            ).read_text(encoding="utf-8")
        )
        result = detect_multilead(leads, 250, cfg)
        self.assertEqual(result["status"], "multilead_candidates_not_adjudicated")
        self.assertGreater(len(result["peaks"]), 0)
        self.assertEqual(result["filtered"].shape, leads.shape)
        with self.assertRaises(ValueError):
            detect_multilead(
                np.where(
                    np.arange(leads.size).reshape(leads.shape) == 0, np.nan, leads
                ),
                250,
                cfg,
            )
