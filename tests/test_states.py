import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from capsaicin.states import describe_states


def fixture(values):
    return [
        dict(
            subject_id="synthetic",
            time_min=t,
            vas=v if isinstance(v, (int, float)) else None,
            status="observed" if isinstance(v, (int, float)) else v,
        )
        for t, v in enumerate(values, 1)
    ]


class StateDescriptionTests(unittest.TestCase):
    def test_no_unjustified_thresholds(self):
        with self.assertRaises(ValueError):
            describe_states(fixture([1, 2]), [3, 6], "")

    def test_exact_threshold_enters_upper_state(self):
        x = describe_states(fixture([0, 3, 6, 10]), [3, 6], "synthetic fixture only")
        self.assertEqual([r["state"] for r in x["points"]], [0, 1, 2, 2])
        self.assertEqual(len(x["transitions"]), 3)

    def test_gap_and_terminal_codes_not_bridged(self):
        source = fixture([1, "missing", 2, 2, "termination_E", "post_termination"])
        x = describe_states(source, [3, 6], "synthetic fixture only")
        self.assertEqual(len(x["transitions"]), 1)
        self.assertEqual(len(x["spells"]), 2)
        self.assertTrue(
            all(s["left_censored"] and s["right_censored"] for s in x["spells"])
        )
        self.assertEqual(x["spells"][-1]["observed_span_min"], 1)

    def test_change_has_observed_boundary_but_not_exact_event_time(self):
        x = describe_states(
            fixture([1, 1, 4, 4, "termination_T"]), [3, 6], "synthetic fixture only"
        )
        a, b = x["spells"]
        self.assertFalse(a["right_censored"])
        self.assertFalse(b["left_censored"])
        self.assertTrue(a["left_censored"])
        self.assertTrue(b["right_censored"])
        self.assertEqual(a["observed_span_min"], 1)

    def test_duplicate_time_rejected(self):
        with self.assertRaises(ValueError):
            describe_states(
                fixture([1]) + fixture([2]), [3, 6], "synthetic fixture only"
            )
