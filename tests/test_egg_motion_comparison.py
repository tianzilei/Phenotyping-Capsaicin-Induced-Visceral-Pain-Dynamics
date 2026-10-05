"""Synthetic paired-comparison contract checks."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from compare_egg_motion_development import compare_rows


class EggMotionComparisonTests(unittest.TestCase):
    def test_paired_metrics_and_identical_person_are_required(self):
        common = dict(
            subject_id="S1",
            recording_stem="R1",
            stage="E",
            pool="development",
            run_status="completed",
        )
        old = [
            dict(
                common,
                status="EGG_CANDIDATE_SPECTRUM_ONLY",
                peak_cpm_weighted="3",
                slow_power_ratio="0.2",
                slow_coherence_descriptive="0.5",
            )
        ]
        new = [
            dict(
                common,
                motion_spectrum_status="MOTION_SCREENED_SPECTRUM_CANDIDATE_ONLY",
                motion_spectrum_peak_cpm_weighted="2.8",
                motion_spectrum_slow_power_ratio="0.3",
                motion_spectrum_coherence_descriptive="0.4",
                motion_candidate_fraction="0.01",
                motion_spectrum_used_seconds="240",
            )
        ]
        pairs, summary = compare_rows(old, new)
        self.assertAlmostEqual(pairs[0]["abs_peak_delta_cpm"], 0.2)
        self.assertEqual(summary["minimum_screened_valid_seconds"], 240)
        new[0]["subject_id"] = "S2"
        with self.assertRaises(ValueError):
            compare_rows(old, new)

    def test_non_development_record_is_rejected(self):
        with self.assertRaises(ValueError):
            compare_rows(
                [
                    dict(
                        subject_id="S",
                        recording_stem="R",
                        stage="E",
                        pool="sealed_validation",
                        run_status="completed",
                    )
                ],
                [],
            )


if __name__ == "__main__":
    unittest.main()
