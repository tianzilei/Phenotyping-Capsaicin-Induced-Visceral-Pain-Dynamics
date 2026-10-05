import unittest

from scripts.build_extended_enc_mapping import (
    parse_extended,
    resolve_claims,
    components,
    unphased_known_alias,
)


class ExtendedMappingTests(unittest.TestCase):
    def test_missing_abbreviation_and_missing_code(self):
        self.assertEqual(parse_extended("20250616223E.acq")["stage"], "E")
        self.assertEqual(parse_extended("20250616ABCDN.acq")["recording_code"], "")

    def test_short_abbreviation_requires_anchor(self):
        row = parse_extended("20241107060ABCE_20241107_163843.OMM")
        self.assertEqual(row["filename_abbr"], "ABC")
        self.assertEqual(row["parse_rule"], "three_letter_abbreviation_requires_anchor")

    def test_no_invented_stage_or_appledouble(self):
        self.assertEqual(parse_extended("20250624222ABXY.acq")["stage"], "")
        self.assertIsNone(parse_extended("._20250616223E.acq"))
        self.assertIsNone(parse_extended("20250616223ABCDA1.acq"))
        self.assertIsNone(parse_extended("20250616223ABCDpart2.acq"))
        self.assertIsNone(parse_extended("20250230223ABCDE.acq"))

    def test_duplicate_extension(self):
        self.assertEqual(parse_extended("20250402157abcdeacq.acq")["stage"], "E")

    def test_conflict_cannot_take_existing_file(self):
        identities = {"S1": ("name1", ("1",)), "S2": ("name2", ("2",))}
        claims = [
            {
                "path": "synthetic",
                "current_subject_id": "S2",
                "priority": 90,
                "supported": True,
            }
        ]
        accepted, review = resolve_claims(claims, identities, {"synthetic": {"S1"}})
        self.assertFalse(accepted)
        self.assertEqual(review[0]["review_reason"], "identity_conflict")

    def test_tied_distinct_owners_and_candidate_only(self):
        identities = {"S1": ("same", ("E",)), "S2": ("same", ("T",))}
        claims = [
            {
                "path": "synthetic",
                "current_subject_id": s,
                "priority": 50,
                "supported": False,
            }
            for s in identities
        ]
        accepted, review = resolve_claims(claims, identities, {})
        self.assertFalse(accepted)
        self.assertTrue(all(r["review_reason"] == "identity_conflict" for r in review))
        accepted, review = resolve_claims(claims[:1], identities, {})
        self.assertFalse(accepted)
        self.assertEqual(
            review[0]["review_reason"], "abbreviation_only_or_visit_unverified"
        )

    def test_unknown_or_acupuncture_phase_cannot_complete(self):
        flags = components(
            [
                {"stage": s, "modality": m}
                for s in ["", "A", "P", "T"]
                for m in ["fnirs", "electrophysiology"]
            ]
        )
        self.assertFalse(any(flags.values()))

    def test_P_remains_P_and_only_supplements_rest(self):
        parsed = parse_extended("20250616223ABCDP_20250616_120000.omm")
        self.assertEqual(parsed["stage"], "P")
        rows = [{"stage": "P", "modality": m} for m in ["fnirs", "electrophysiology"]]
        self.assertFalse(any(components(rows).values()))
        flags = components(rows, ("N", "C", "P"))
        self.assertTrue(flags["fnirs_pre_rest"])
        self.assertTrue(flags["electrophysiology_pre_rest"])
        self.assertFalse(flags["fnirs_E"])
        self.assertFalse(flags["electrophysiology_E"])
        for phase in ["A", "T", "B", "A1", "T2", "B3"]:
            self.assertIsNone(parse_extended(f"20250616223ABCD{phase}.acq"))

    def test_known_alias_ending_in_stage_requires_complementary_files(self):
        row = parse_extended("20250616223ABCE.omm")
        key = (row["date"], row["recording_code"], row["filename_abbr"])
        self.assertTrue(unphased_known_alias(row, {"ABCE": {"S1"}}, {key: {"E"}}))
        self.assertFalse(unphased_known_alias(row, {"ABCE": {"S1"}}, {key: {"E", "N"}}))


if __name__ == "__main__":
    unittest.main()
