"""Synthetic checks for non-interpolated RR candidate construction."""

import unittest

from capsaicin.ecg_rr_candidates_v2 import (
    classify_rr_values,
    enforce_refractory,
    rr_candidates,
    rr_summary,
    symmetric_rr_continuity,
)


class EcgRrCandidateTests(unittest.TestCase):
    def test_refractory_prefers_more_lead_votes(self):
        kept = enforce_refractory(
            [(100, 2), (250, 3), (1000, 2)], fs=1000, refractory_seconds=0.2
        )
        self.assertEqual(kept, [(250, 3), (1000, 2)])

    def test_rr_flags_do_not_interpolate_or_call_nn(self):
        rows = rr_candidates([(0, 3), (1000, 2), (2050, 3), (5000, 3)], fs=1000)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["status"], "RR_CANDIDATE_FLAGGED")
        self.assertIn("not_nn", rows[0]["semantic_status"])
        summary = rr_summary(rows)
        self.assertEqual(summary["rr_candidates"], 3)
        self.assertIn("not_nn", summary["rmssd_semantics"])

    def test_isolated_single_lead_events_are_excluded(self):
        rows = rr_candidates([(0, 1), (1000, 2), (2000, 2)], fs=1000)
        self.assertEqual(len(rows), 1)

    def test_rmssd_does_not_bridge_a_flagged_interval(self):
        rows = rr_candidates([(0, 3), (1000, 3), (4000, 3), (5000, 3)], fs=1000)
        summary = rr_summary(rows)
        self.assertIsNone(summary["candidate_rmssd_seconds"])

    def test_flag_starts_new_block_without_cascade(self):
        rows = rr_candidates(
            [(0, 3), (1000, 3), (1500, 3), (2500, 3), (3500, 3)], fs=1000
        )
        self.assertEqual(
            [row["status"] for row in rows],
            [
                "RR_CANDIDATE_LOCALLY_PLAUSIBLE",
                "RR_CANDIDATE_FLAGGED",
                "RR_CANDIDATE_LOCALLY_PLAUSIBLE",
                "RR_CANDIDATE_LOCALLY_PLAUSIBLE",
            ],
        )
        self.assertTrue(rows[2]["relock_boundary"])
        self.assertEqual(rows[2]["local_block_id"], 1)

    def test_reverse_pass_returns_original_interval_order(self):
        flags = classify_rr_values([1.0, 0.7, 1.0], jump_fraction=0.25, reverse=True)
        self.assertEqual(len(flags), 3)
        self.assertEqual(flags[1]["status"], "RR_CANDIDATE_FLAGGED")

    def test_symmetric_continuity_is_time_reversal_invariant(self):
        values = [1.0, 1.05, 0.7, 1.02, 3.0, 1.0, 1.04]
        forward = symmetric_rr_continuity(values)
        reverse = symmetric_rr_continuity(list(reversed(values)))
        self.assertEqual(
            forward["range_valid"].tolist(),
            list(reversed(reverse["range_valid"].tolist())),
        )
        self.assertEqual(
            forward["edge_continuous"].tolist(),
            list(reversed(reverse["edge_continuous"].tolist())),
        )

    def test_symmetric_discontinuity_splits_edge_without_endpoint_label(self):
        result = symmetric_rr_continuity([1.0, 1.02, 0.70, 0.71])
        self.assertEqual(result["edge_continuous"].tolist(), [True, False, True])
        self.assertEqual(result["block_ids"].tolist(), [0, 0, 1, 1])


if __name__ == "__main__":
    unittest.main()
