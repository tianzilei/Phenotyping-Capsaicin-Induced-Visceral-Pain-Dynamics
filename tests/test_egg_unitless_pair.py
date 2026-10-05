"""Strict-pair contract checks for advisory EGG probes."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pair_egg_unitless_probes import pair_rows


class EggUnitlessPairTests(unittest.TestCase):
    def row(self, stage, value):
        return dict(
            subject_id="S",
            recording_stem="R",
            stage=stage,
            pool="development",
            run_status="completed",
            subslow_ratio_max=str(value),
            exact_repeat_fraction_max=str(value / 10),
            ecg_egg_harmonic_coherence_max=str(value / 2),
        )

    def test_strict_pair_and_signed_differences(self):
        paired = pair_rows([self.row("N", 0.2), self.row("E", 0.5)])
        self.assertEqual(len(paired), 1)
        self.assertAlmostEqual(
            paired[0]["stimulus_minus_baseline_subslow_ratio_max"], 0.3
        )

    def test_unpaired_or_application_rows_fail(self):
        with self.assertRaises(ValueError):
            pair_rows([self.row("E", 0.5)])
        bad = self.row("N", 0.2)
        bad["pool"] = "application"
        with self.assertRaises(ValueError):
            pair_rows([bad])


if __name__ == "__main__":
    unittest.main()
