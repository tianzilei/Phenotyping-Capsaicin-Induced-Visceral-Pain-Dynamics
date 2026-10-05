import unittest
from capsaicin.sync_verification import (
    complete_vas,
    cluster_edges,
    audit_offsets,
    match_offset,
)

CFG = dict(
    match_tolerance_seconds=0.25,
    minimum_matches=3,
    minimum_span_seconds=100,
    alternative_match_count_margin=2,
    distinct_offset_seconds=1,
)


class SyncVerificationTests(unittest.TestCase):
    def test_complete_preserves_zero_rejects_markers_and_nonfinite(self):
        row = {f"VAS_{i}min": "0" for i in range(1, 21)}
        self.assertTrue(complete_vas(row))
        for bad in ("E", "T", "", "NA", "nan", "inf", "-1", "11", None):
            self.assertFalse(complete_vas(dict(row, VAS_3min=bad)))
        del row["VAS_5min"]
        self.assertFalse(complete_vas(row))

    def test_ttl_burst_not_repeated_minute(self):
        self.assertEqual(
            cluster_edges([1, 1.001, 1.095, 1.096, 61], 0.2),
            [[1, 1.001, 1.095, 1.096], [61]],
        )
        with self.assertRaises(ValueError):
            cluster_edges([2, 1], 0.2)

    def test_periodic_alias_not_certified(self):
        a = list(range(0, 1200, 60))
        b = [x + 5 for x in a]
        self.assertEqual(
            audit_offsets(a, b, CFG)["status"], "ambiguous_periodic_offset"
        )

    def test_irregular_unique_missing_extra(self):
        a = [0, 31, 104, 225, 406, 677, 941, 1281]
        b = sorted([x + 7 for x in a if x != 225] + [555])
        r = audit_offsets(a, b, CFG)
        self.assertEqual(r["status"], "unique_clock_candidate_needs_event_anchor")
        self.assertAlmostEqual(r["offset_s"], 7)
        self.assertEqual(r["matches"], 7)

    def test_missing_no_nearest_forced_match(self):
        self.assertEqual(audit_offsets([], [1], CFG)["status"], "missing_events")
        self.assertEqual(match_offset([1, 2], [1.1], 0, 0.2), [(0, 0)])
        with self.assertRaises(ValueError):
            audit_offsets([1, 1], [2], CFG)
