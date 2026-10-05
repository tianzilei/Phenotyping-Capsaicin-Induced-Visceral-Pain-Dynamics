import unittest

from scripts.build_enc_signal_inventory import parse_recording_name


class EncRecordingNameTests(unittest.TestCase):
    def test_converted_fnirs_uses_last_pre_underscore_stage(self):
        parsed = parse_recording_name("20241020001GYXINE_20241020_165304.snirf")
        self.assertEqual(parsed["recording_code"], "1")
        self.assertEqual(parsed["filename_abbr"], "GYXI")
        self.assertEqual(parsed["stage"], "E")

    def test_missing_code_leading_zero_and_lowercase_stage(self):
        parsed = parse_recording_name("2024110358XXYUc.csv")
        self.assertEqual(parsed["recording_code"], "58")
        self.assertEqual(parsed["stage"], "C")

    def test_egg_suffix_is_not_mistaken_for_stage(self):
        parsed = parse_recording_name("20250622255cjxin_egg.csv")
        self.assertEqual(parsed["filename_abbr"], "CJXI")
        self.assertEqual(parsed["stage"], "N")

    def test_non_enc_phase_is_parsed_but_excluded(self):
        parsed = parse_recording_name("20250611218ZJYUa1.acq")
        self.assertEqual(parsed["phase"], "A")
        self.assertEqual(parsed["stage"], "")


if __name__ == "__main__":
    unittest.main()
