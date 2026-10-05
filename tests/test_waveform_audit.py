import unittest
import numpy as np
from capsaicin.waveform_audit import describe, agreement


class WaveformAuditTests(unittest.TestCase):
    def test_nan_breaks_constant_run(self):
        r = describe([2, 2, np.nan, 2, 2, 2], 2)
        self.assertEqual(r["longest_constant_samples"], 3)
        self.assertEqual(r["longest_constant_span_s"], 1)
        self.assertEqual(r["nonfinite"], 1)
        self.assertFalse(r["whole_constant"])

    def test_all_missing_and_singleton(self):
        self.assertEqual(describe([np.nan, np.inf], 2)["longest_constant_samples"], 0)
        self.assertIsNone(describe([np.nan], 2)["min_native"])
        self.assertEqual(describe([0], 2)["longest_constant_span_s"], 0)

    def test_timing_and_exact_constant(self):
        r = describe(np.zeros(2001), 2000)
        self.assertEqual(r["longest_constant_span_s"], 1)
        self.assertTrue(r["whole_constant"])
        with self.assertRaises(ValueError):
            describe([1], 0)

    def test_decimation_and_lost_first_row(self):
        x = np.arange(80.0)
        self.assertTrue(agreement(x, x[1::8], 8, 1, 1e-6)["matches"])
        self.assertFalse(agreement(x, x[1:], 1, 0, 1e-6)["eligible"])
        self.assertFalse(agreement(x, x + 0.1, 1, 0, 1e-6)["matches"])
        self.assertTrue(agreement(x, x + 0.0000004, 1, 0, 1e-6)["matches"])
