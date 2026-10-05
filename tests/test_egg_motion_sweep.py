"""Scenario summary checks for the EGG motion-proxy sensitivity sweep."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_egg_motion_sweep import summarize


class EggMotionSweepTests(unittest.TestCase):
    def row(
        self,
        multiple,
        reference,
        peak,
        status="MOTION_SCREENED_SPECTRUM_CANDIDATE_ONLY",
    ):
        return dict(
            subject_id="S",
            recording_stem="R",
            stage="E",
            mad_multiple=multiple,
            reference_seconds=reference,
            support_status="MOTION_SCREENED_CANDIDATE_SUPPORT",
            motion_spectrum_status=status,
            motion_spectrum_peak_cpm_weighted=peak,
            motion_candidate_fraction=0.01,
        )

    def test_anchor_delta_is_calculated_without_selecting_scenario(self):
        rows = [self.row(8, 60, 3.0), self.row(6, 45, 3.4)]
        summary = summarize(rows)
        changed = next(row for row in summary if row["mad_multiple"] == 6)
        self.assertAlmostEqual(changed["maximum_abs_peak_delta_from_anchor_cpm"], 0.4)
        self.assertIn("no_selected", changed["interpretation"])

    def test_missing_anchor_fails(self):
        with self.assertRaises(ValueError):
            summarize([self.row(6, 45, 3.4)])


if __name__ == "__main__":
    unittest.main()
