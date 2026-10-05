import unittest
from capsaicin.rest_state import choose_rest_stage, is_rest_reference_eligible


class RestStateTests(unittest.TestCase):
    def test_n_c_require_strict_mapping(self):
        self.assertTrue(
            is_rest_reference_eligible(
                {"stage": "N", "match_status": "accepted_strict"}
            )
        )
        self.assertFalse(
            is_rest_reference_eligible(
                {"stage": "C", "match_status": "accepted_relaxed"}
            )
        )

    def test_p_requires_reviewed_explicit_support(self):
        row = {
            "stage": "P",
            "supported": "True",
            "rule_version": "enc_matching_v3",
            "parse_rule": "explicit_phase",
        }
        self.assertTrue(is_rest_reference_eligible(row))
        self.assertFalse(is_rest_reference_eligible({**row, "supported": "False"}))

    def test_priority_does_not_merge_or_relabel(self):
        self.assertEqual(choose_rest_stage(["P", "C"]), "C")
        self.assertEqual(choose_rest_stage(["P"]), "P")
        self.assertIsNone(choose_rest_stage(["E"]))


if __name__ == "__main__":
    unittest.main()
