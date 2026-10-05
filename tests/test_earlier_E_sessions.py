import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from freeze_earlier_E_sessions import earlier_date_candidates


class EarlierDates(unittest.TestCase):
    def test_actual_date_not_filename_or_input_order(self):
        a = dict(filename="20200101.acq", acquisition_dates=["2025-06-01"])
        b = dict(filename="20251231.acq", acquisition_dates=["2025-03-01"])
        self.assertEqual(earlier_date_candidates([a, b]), [b])
        self.assertEqual(earlier_date_candidates([b, a]), [b])

    def test_same_day_ties_are_preserved(self):
        rows = [dict(acquisition_dates=["2025-03-01"], sha256=s) for s in ["a", "b"]]
        self.assertEqual(earlier_date_candidates(rows), rows)

    def test_unknown_or_multiday_rejected(self):
        for rows in [
            [],
            [dict(acquisition_dates=[])],
            [dict(acquisition_dates=["2025-01-01", "2025-01-02"])],
        ]:
            with self.assertRaises(ValueError):
                earlier_date_candidates(rows)
