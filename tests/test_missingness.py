import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import unittest
from capsaicin.missingness import classify_subject, adjacent_composition


def rows(vals):
    out = []
    marker = ""
    for t, v in enumerate(vals, 1):
        if v in ("E", "T"):
            marker = v
            out.append(
                dict(time_min=t, status="termination_" + v, termination_code=marker)
            )
        elif v is None:
            out.append(
                dict(
                    time_min=t,
                    status="post_termination" if marker else "missing",
                    termination_code=marker,
                )
            )
        else:
            out.append(
                dict(
                    time_min=t, status="observed", termination_code=marker, vas=float(v)
                )
            )
    return out


class MissingnessTests(unittest.TestCase):
    def test_pre_and_post_marker_are_distinct(self):
        z = classify_subject(rows([1, None, 2, "E", None, None]), range(1, 7))
        self.assertEqual(z["n_pre_marker_missing"], 1)
        self.assertEqual(z["n_post_termination_missing"], 2)
        self.assertEqual(z["longest_pre_marker_gap"], 1)
        self.assertEqual(z["last_observed_min"], 3)
        self.assertIn("pre_marker_missing", z["pattern"])
        self.assertIn("post_termination_missing", z["pattern"])

    def test_no_marker_missing_is_pre_marker(self):
        z = classify_subject(rows([1, None, 2, None]), range(1, 5))
        self.assertEqual(z["eventual_marker"], "none")
        self.assertEqual(z["n_pre_marker_missing"], 2)
        self.assertEqual(z["n_post_termination_missing"], 0)

    def test_t_marker_and_no_mutation(self):
        source = rows([1, 2, "T", None])
        snapshot = [dict(x) for x in source]
        z = classify_subject(source, range(1, 5))
        self.assertEqual(z["eventual_marker"], "T")
        self.assertEqual(z["first_marker_min"], 3)
        self.assertEqual(source, snapshot)

    def test_missing_scheduled_minute_rejected(self):
        with self.assertRaises(ValueError):
            classify_subject(rows([1, 2]), range(1, 4))

    def test_composition_change_without_within_person_change(self):
        r = [
            dict(subject_id=s, time_min=t, status="observed", vas=v)
            for s, t, v in [("a", 1, 0), ("b", 1, 10), ("b", 2, 10)]
        ]
        z = adjacent_composition(r, range(1, 3))[0]
        self.assertEqual(z["observed_mean_change"], 5)
        self.assertEqual(z["paired_observed_change"], 0)
        self.assertEqual(z["composition_total"], 5)
        self.assertEqual(z["n_leaving"], 1)

    def test_entering_and_no_overlap_not_filled(self):
        r = [
            dict(subject_id=s, time_min=t, status="observed", vas=v)
            for s, t, v in [("a", 1, 1), ("a", 2, 2), ("b", 2, 8), ("c", 3, 4)]
        ]
        a, b = adjacent_composition(r, range(1, 4))
        self.assertEqual(a["observed_mean_change"], 4)
        self.assertEqual(a["paired_observed_change"], 1)
        self.assertEqual(a["end_composition"], 3)
        self.assertFalse(b["defined"])
        self.assertIsNone(b["paired_observed_change"])

    def test_duplicate_minutes_rejected(self):
        with self.assertRaises(ValueError):
            classify_subject(rows([1]) + rows([2]), range(1, 2))
