import unittest
from capsaicin.paired_candidate_change import (
    bootstrap_median_interval,
    rank_change_summary,
    strict_pair,
)


class PairedCandidateTests(unittest.TestCase):
    def test_strict_pair_requires_one_baseline(self):
        rows = [
            {"subject_id": "S", "recording_stem": "R", "stage": "N"},
            {"subject_id": "S", "recording_stem": "R", "stage": "E"},
        ]
        self.assertEqual(len(strict_pair(rows)), 1)
        self.assertEqual(
            strict_pair(
                rows + [{"subject_id": "S", "recording_stem": "R", "stage": "C"}]
            )[0][1],
            "N",
        )

    def test_p_is_an_eligible_rest_stage(self):
        rows = [
            {"subject_id": "S", "recording_stem": "R", "stage": "P"},
            {"subject_id": "S", "recording_stem": "R", "stage": "E"},
        ]
        self.assertEqual(strict_pair(rows)[0][1], "P")

    def test_bootstrap_is_reproducible(self):
        self.assertEqual(
            bootstrap_median_interval([1, 2, 3], replicates=50),
            bootstrap_median_interval([1, 2, 3], replicates=50),
        )

    def test_rank_summary_reports_loo_range(self):
        result = rank_change_summary([1, 2, 3, 4], [1, 2, 4, 3])
        self.assertIsNotNone(result["spearman_rho"])
        self.assertIsNotNone(result["leave_one_out_min"])


if __name__ == "__main__":
    unittest.main()
