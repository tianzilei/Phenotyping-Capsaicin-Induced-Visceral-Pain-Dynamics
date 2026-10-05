import unittest
from scripts.reverse_unmatched_enc import parse_reverse, log_support


class ReverseEncTests(unittest.TestCase):
    def test_excluded_stages_and_arbitrary_suffixes(self):
        for name in [
            "20250620244ABCDP.acq",
            "20250620244ABCDA1.acq",
            "20250620244ABCDT2.acq",
            "20250620244ABCDB3.acq",
            "._20250620244ABCDE.acq",
        ]:
            self.assertIsNone(parse_reverse(name))
        self.assertIsNone(parse_reverse("20250508009PHASETASK.csv"))

    def test_case_suffix_and_short_abbreviation(self):
        r = parse_reverse("20250620244abcde_egg.csv")
        self.assertEqual(
            (r["stage"], r["raw_participant_prefix"]), ("E", "20250620244ABCD")
        )
        self.assertEqual(
            parse_reverse("20250620060ABCE_20250620_120000.omm")["parse_status"],
            "short_abbreviation_ambiguous",
        )
        self.assertEqual(parse_reverse("20250620244ABCDNE.snirf")["stage"], "E")

    def test_log_date_corrects_malformed_stem_only_with_anchor(self):
        f = parse_reverse("202506244ABCDE.acq")
        subject = {"current_subject_id": "S1", "legacy_code_numeric": "244"}
        log = {
            "participant": "202506244ABCD",
            "actual_date": "20250620",
            "recording_code": "4",
            "abbreviation": "ABCD",
        }
        basis, _ = log_support(f, subject, {"ABCD"}, [log], {("20250620", "ABCD")})
        self.assertTrue(basis)
        self.assertFalse(log_support(f, subject, {"ABCD"}, [log], set())[0])
        self.assertFalse(
            log_support(f, subject, {"EFGH"}, [log], {("20250620", "ABCD")})[0]
        )

    def test_short_abbreviation_requires_log_code_date_and_alias(self):
        f = parse_reverse("20241107060ABCE.omm")
        subject = {"current_subject_id": "S1", "legacy_code_numeric": "60"}
        log = {
            "participant": "20241107060ABCD",
            "actual_date": "20241107",
            "recording_code": "60",
            "abbreviation": "ABCD",
        }
        self.assertTrue(log_support(f, subject, {"ABCD"}, [log], set())[0])
        log["actual_date"] = "20241108"
        self.assertFalse(log_support(f, subject, {"ABCD"}, [log], set())[0])
        self.assertFalse(log_support(f, subject, {"ABCD"}, [], set())[0])


if __name__ == "__main__":
    unittest.main()
