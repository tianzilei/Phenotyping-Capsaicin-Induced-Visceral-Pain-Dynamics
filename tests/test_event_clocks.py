import unittest
from capsaicin.event_clocks import (
    finite_number,
    hms_seconds,
    observed_intervals,
    digital_pulses,
)


class EventClockTests(unittest.TestCase):
    def test_missing_and_nonfinite_not_zero(self):
        for value in ("", "nan", "inf", "T", None):
            self.assertIsNone(finite_number(value))
        self.assertEqual(finite_number("0"), 0)

    def test_hms(self):
        self.assertAlmostEqual(hms_seconds("01:02:19.23"), 3739.23)
        for value in ("00:60:00", "00:00:nan", "-1:00:00", "1.5:00:00", "19.23"):
            with self.assertRaises(ValueError):
                hms_seconds(value)

    def test_observed_intervals_preserve_gaps_and_resets(self):
        rows = [{"t": "60"}, {"t": ""}, {"t": "180"}, {"t": ".01"}]
        gaps = observed_intervals(rows, "t")
        self.assertEqual(gaps[0]["intervening_csv_rows"], 1)
        self.assertEqual(gaps[0]["interval_native"], 120)
        self.assertLess(gaps[1]["interval_native"], 0)
        self.assertEqual(len(rows), 4)

    def test_pulses_require_closed_ordered_excursion(self):
        def e(t, a, b):
            return dict(time_from_recording_start_s=t, previous_native=a, next_native=b)

        pulses = digital_pulses([e(0, 5, 0), e(1, 0, 5), e(1.1, 5, 0), e(2, 0, 5)])
        self.assertEqual(len(pulses), 1)
        self.assertAlmostEqual(pulses[0]["duration_s"], 0.1)
        self.assertEqual(digital_pulses([e(2, 0, 5), e(1, 5, 0)]), [])
        self.assertEqual(digital_pulses([e(1, 0, 5), e(2, 4, 0)]), [])
