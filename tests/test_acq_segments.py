import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from capsaicin.acq_segments import segment_bounds


class SegmentTests(unittest.TestCase):
    def test_pause_requires_decision_and_selected_segment_is_not_concatenated(self):
        with self.assertRaises(ValueError):
            segment_bounds(1000, 100, [0, 300])
        d = dict(
            segment_index=1,
            segment_count=2,
            start_sample=300,
            end_sample=1000,
            sampling_hz=100,
        )
        self.assertEqual(segment_bounds(1000, 100, [0, 300], d), (300, 1000))
        d.update(segment_index=0, start_sample=0, end_sample=300)
        self.assertEqual(segment_bounds(1000, 100, [0, 300], d), (0, 300))

    def test_changed_rate_bounds_and_invalid_order_rejected(self):
        d = dict(
            segment_index=1,
            segment_count=2,
            start_sample=300,
            end_sample=1000,
            sampling_hz=100,
        )
        for n, fs, starts in [
            (1000, 200, [0, 300]),
            (1001, 100, [0, 300]),
            (1000, 100, [0, 301]),
            (1000, 100, [0, 0]),
        ]:
            with self.assertRaises(ValueError):
                segment_bounds(n, fs, starts, d)

    def test_single_continuous_record(self):
        self.assertEqual(segment_bounds(1000, 100, [0]), (0, 1000))
