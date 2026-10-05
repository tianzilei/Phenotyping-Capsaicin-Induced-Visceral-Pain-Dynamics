import unittest

from scripts.build_relaxed_enc_mapping import (
    code,
    reviewed_mapping_resolution,
    source_identity_name,
    split_tokens,
    vas_signature,
)
from capsaicin.participant_matching import levenshtein


class RelaxedMappingHelperTests(unittest.TestCase):
    def test_code_removes_prefix_and_leading_zero(self):
        self.assertEqual(code("Z001"), "1")

    def test_split_tokens_normalizes_and_deduplicates(self):
        self.assertEqual(split_tokens("gyxi; GUXI;gyxi"), ["GUXI", "GYXI"])

    def test_vas_signature_preserves_termination_tokens(self):
        row = {"VAS_1min": "3", "VAS_2min": "E"}
        signature = vas_signature(row)
        self.assertEqual(signature[:2], ("3", "E"))

    def test_same_name_different_vas_is_not_the_same_identity(self):
        first = {"VAS_1min": "1", "VAS_2min": "2"}
        second = {"VAS_1min": "1", "VAS_2min": "3"}
        self.assertNotEqual(vas_signature(first), vas_signature(second))

    def test_one_character_abbreviation_typo(self):
        self.assertEqual(levenshtein("LYYA", "LJYA"), 1)

    def test_source_workbook_name_precedes_shifted_legacy_bridge_name(self):
        row = {"xlsx_name": "唐启玥", "bridge_name": "张雪颖"}
        self.assertEqual(source_identity_name(row), "唐启玥")
        self.assertEqual(
            reviewed_mapping_resolution(row, "TQYU", {"TQYU"}),
            (
                "source_workbook_code_vas_identity_overrides_stale_legacy_name",
                "high",
                98,
            ),
        )

    def test_reviewed_large_abbreviation_variant_is_retained_for_audit(self):
        row = {"xlsx_name": "吴应全", "bridge_name": "吴应全"}
        self.assertEqual(
            reviewed_mapping_resolution(row, "WYGA", {"WYQU"}),
            ("same_source_identity_reviewed_abbreviation_variant", "medium", 80),
        )


if __name__ == "__main__":
    unittest.main()
