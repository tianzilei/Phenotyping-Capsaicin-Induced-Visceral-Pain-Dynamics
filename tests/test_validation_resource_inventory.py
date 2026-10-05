"""Synthetic boundary checks for resource counts, never real participant data."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from inventory_validation_resources import time_segments, available, bound
import numpy as np


class ResourceInventoryTests(unittest.TestCase):
    def test_pause_is_not_bridged_by_total_record_duration(self):
        t = np.r_[np.arange(0.0, 201.0), np.arange(250.0, 451.0)]
        segments, _ = time_segments(t)
        self.assertEqual(segments, [(0.0, 200.0), (250.0, 450.0)])
        self.assertFalse(available(segments, 0.0, 300.0))

    def test_no_endpoint_extension_or_float_rounding_to_full_window(self):
        self.assertFalse(available([(0.0, 299.982)], 0.0, 300.0))
        self.assertTrue(available([(0.0, 300.0)], 0.0, 300.0))

    def test_invalid_time_is_rejected(self):
        for t in [[0, 1, 1], [0, float("nan"), 2], [1, 0]]:
            with self.assertRaises(ValueError):
                time_segments(np.array(t, float))

    def test_zero_error_bound_requires_59_independent_accepts(self):
        self.assertGreater(bound(58), 0.05)
        self.assertLessEqual(bound(59), 0.05)
        self.assertIsNone(bound(0))
