import unittest
from datetime import datetime, timedelta
from scripts.match_orphans_by_time import (
    filename_time,
    log_interval,
    interval_gap,
    supported_time_match,
)


class TimeLinkageTests(unittest.TestCase):
    def test_embedded_time_ignores_filename_prefix_date(self):
        self.assertEqual(
            filename_time("20250101001ABCDE_20250102_123456.omm"),
            datetime(2025, 1, 2, 12, 34, 56),
        )
        self.assertIsNone(filename_time("20250101001ABCDE.csv"))

    def test_log_interval_preserves_elapsed_time_and_rejects_conflicting_start(self):
        rows = [
            {
                "expStart": "2025-01-02 12h00.00.000000 +0800",
                "eval.started": "600",
                "eval.stopped": "660",
            }
        ]
        self.assertEqual(
            log_interval(rows), (datetime(2025, 1, 2, 12), datetime(2025, 1, 2, 12, 11))
        )
        self.assertIsNone(
            log_interval(rows + [{"expStart": "2025-01-02 13h00.00.000000 +0800"}])
        )

    def test_same_date_alone_cannot_match_and_competing_interval_blocks(self):
        t = datetime(2025, 1, 2, 12)
        own = [(t - timedelta(minutes=10), t)]
        self.assertFalse(supported_time_match(True, False, own, [], t, 300))
        self.assertFalse(supported_time_match(False, True, own, [], t, 300))
        self.assertFalse(supported_time_match(True, True, own, own, t, 300))
        self.assertTrue(
            supported_time_match(True, True, own, [], t + timedelta(seconds=299), 300)
        )
        self.assertFalse(
            supported_time_match(True, True, own, [], t + timedelta(seconds=301), 300)
        )


if __name__ == "__main__":
    unittest.main()
