import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from capsaicin.readiness import readiness


class ReadinessTests(unittest.TestCase):
    def test_empty_metadata_does_not_approve_science(self):
        self.assertTrue(all(not x["ready"] for x in readiness({}).values()))

    def test_file_mapping_does_not_imply_qc(self):
        r = readiness({"identity_verified": True, "files_exist": True})
        self.assertIn(
            "signal_artifact_qc_not_passed", r["physiology_association"]["reasons"]
        )

    def test_invalid_thresholds_rejected(self):
        for thresholds in ([3, 3], [6, 3], [float("nan")], [0], [10], [True]):
            self.assertIn(
                "state_thresholds_invalid",
                readiness({"state_thresholds": thresholds})["markov"]["reasons"],
            )

    def test_thresholds_alone_do_not_validate_estimator(self):
        r = readiness(
            {
                "state_thresholds": [3, 6],
                "state_threshold_rationale": "synthetic fixture",
                "transition_information_rule": "synthetic fixture",
            }
        )
        self.assertEqual(r["markov"]["reasons"], ["state_estimator_not_validated"])
