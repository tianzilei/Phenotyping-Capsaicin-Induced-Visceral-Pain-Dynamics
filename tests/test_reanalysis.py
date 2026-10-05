import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
from capsaicin.reanalysis import (
    unify_people,
    vas_support,
    match_peaks,
    rr_metrics,
    time_weights,
    source_mapping_admission,
)


class Contracts(unittest.TestCase):
    def test_alias_covariates_not_averaged(self):
        a = dict(ID="a", age="20", **{f"VAS_{i}min": "1" for i in range(1, 21)})
        b = dict(a, ID="b", age="22")
        rows, conflicts, registry = unify_people([a, b], {"b": "a"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["age"], "")
        self.assertEqual(len(conflicts), 2)
        b["VAS_1min"] = "2"
        with self.assertRaises(ValueError):
            unify_people([a, b], {"b": "a"})

    def test_alias_covariates_choose_smallest_numeric_id(self):
        a = dict(
            ID="SYN_SUBJECT021",
            age="20",
            weight="67",
            **{f"VAS_{i}min": "1" for i in range(1, 21)},
        )
        b = dict(
            ID="SYN_SUBJECT213",
            age="22",
            weight="65",
            **{f"VAS_{i}min": "1" for i in range(1, 21)},
        )
        rows, conflicts, _ = unify_people(
            [b, a],
            {"SYN_SUBJECT213": "SYN_SUBJECT021"},
            conflict_policy="smallest_numeric_id",
        )
        self.assertEqual(rows[0]["age"], "20")
        self.assertEqual(rows[0]["weight"], "67")
        self.assertTrue(
            all(c["selected_source_alias"] == "SYN_SUBJECT021" for c in conflicts)
        )
        self.assertTrue(
            all(c["selection_rule"] == "smallest_numeric_id" for c in conflicts)
        )

    def test_minutes_not_bridged(self):
        r = {f"VAS_{i}min": str(i) for i in [1, 3, 5]}
        self.assertIsNone(vas_support(r, 0, "B"))
        r.update(VAS_2min="2")
        self.assertEqual(vas_support(r, 0, "B")["end_s"], 180)
        self.assertIsNone(vas_support(r, 0, "A"))

    def test_matching_count_and_error(self):
        self.assertEqual(match_peaks([0, 0.05], [0.04], 0.05), [(1, 0)])
        self.assertEqual(match_peaks([0, 0.09], [0.05, 0.14], 0.06), [(0, 0), (1, 1)])
        self.assertEqual(match_peaks([], [], 0.05), [])

    def test_rr_no_bridge(self):
        m = rr_metrics([0, 1, 2, 3.5, 5], [1, 1, 0, 1, 1])
        self.assertEqual(m["rr_count"], 2)
        self.assertIsNone(m["rr_rmssd_ms"])
        self.assertEqual(rr_metrics([0, 1, 2, 3], [1, 1, 1, 1])["rr_rmssd_ms"], 0)

    def test_time_gap_and_endpoints(self):
        t = np.array([0, 1, 2, 5, 6], float)
        self.assertEqual(time_weights(t, 0, 6).sum(), 3)
        with self.assertRaises(ValueError):
            time_weights([0, 1, 1], 0, 2)

    def test_source_mapping_admission_accepts_all_algorithm_statuses(self):
        admission = {
            "accepted_match_statuses": [
                "accepted_strict",
                "accepted_relaxed",
                "accepted_relaxed_session_expansion",
            ],
            "required_fields": [
                "current_subject_id",
                "path",
                "filename",
                "extension",
                "stage",
                "match_status",
            ],
            "eligible_stages": ["E", "N", "C"],
        }
        base = dict(
            current_subject_id="SYN_SUBJECT001",
            path="x",
            filename="x.acq",
            extension=".acq",
            stage="E",
        )
        for status in admission["accepted_match_statuses"]:
            ok, reason = source_mapping_admission(
                dict(base, match_status=status), admission
            )
            self.assertTrue(ok, reason)
        ok, reason = source_mapping_admission(dict(base, match_status=""), admission)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
