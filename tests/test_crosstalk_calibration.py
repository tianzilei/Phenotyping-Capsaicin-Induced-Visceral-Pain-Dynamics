import unittest
import numpy as np

from capsaicin.crosstalk_calibration import (
    CalibrationSpec,
    classify_attenuation,
    estimate_template,
    session_slices,
    subtract_frozen_template,
)


class CrosstalkCalibrationTests(unittest.TestCase):
    def test_short_session_is_rejected(self):
        with self.assertRaises(ValueError):
            session_slices(200 * 100, 100)

    def test_zero_input_cannot_inject_template(self):
        fs = 100.0
        spec = CalibrationSpec()
        t = np.zeros(300 * int(fs))
        peaks = np.arange(1, 299) * int(fs)
        template = np.ones((1, 25))
        out, info = subtract_frozen_template(t, peaks, template, fs, spec)
        np.testing.assert_array_equal(out, t)
        self.assertEqual(info["applied_windows"], 0)

    def test_synthetic_template_subtraction_preserves_length(self):
        fs = 100.0
        rng = np.random.default_rng(4)
        n = 300 * int(fs)
        peaks = np.arange(1, 299) * int(fs)
        base = np.sin(2 * np.pi * 3 * np.arange(n) / (60 * fs))
        template = np.exp(-0.5 * (np.arange(25) - 10) ** 2 / 3**2)[None, :]
        x = base.copy()
        for p in peaks:
            x[p - 10 : p + 15] += template[0]
        out, info = subtract_frozen_template(x, peaks, template, fs)
        self.assertEqual(len(out), n)
        self.assertGreater(info["applied_windows"], 0)
        self.assertTrue(np.all(np.isfinite(out)))

    def test_legacy_and_exploratory_gates_are_distinct(self):
        d = classify_attenuation(8.0, True)
        self.assertTrue(d["pass_6db_exploratory"])
        self.assertFalse(d["pass_15db_legacy"])


if __name__ == "__main__":
    unittest.main()
