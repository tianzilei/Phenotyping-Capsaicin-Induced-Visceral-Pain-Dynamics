import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from capsaicin.signal_time import expand_snirf_time


class SignalTimeTests(unittest.TestCase):
    def test_start_step_compact_time(self):
        self.assertEqual(expand_snirf_time([2, 0.5], 4), [2, 2.5, 3, 3.5])

    def test_actual_two_sample_vector(self):
        self.assertEqual(expand_snirf_time([2, 3], 2), [2, 3])

    def test_irregular_actual_time_preserved(self):
        self.assertEqual(expand_snirf_time([0, 1, 3], 3), [0, 1, 3])

    def test_invalid_time_rejected(self):
        for times, n in [
            ([1, 1, 2], 3),
            ([0, -1], 4),
            ([0, 1, 2], 4),
            ([float("nan"), 1], 4),
        ]:
            with self.assertRaises(ValueError):
                expand_snirf_time(times, n)
