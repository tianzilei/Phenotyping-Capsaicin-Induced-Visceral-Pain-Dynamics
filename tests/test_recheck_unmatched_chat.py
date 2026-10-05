import unittest
from scripts.recheck_unmatched_chat import named_line, can_correct


class ChatRecheckTests(unittest.TestCase):
    def test_correction_prefix_and_code(self):
        self.assertEqual(named_line("更正：Z199测试甲--29测试乙a1", "测试甲"), "199")
        self.assertIsNone(named_line("Z199测试甲--29测试乙a1", "测试乙"))
        self.assertEqual(named_line("313测试甲健康2", "测试甲"), "313")

    def test_code_correction_requires_chat_and_other_device(self):
        subjects = {
            "S1": {"xlsx_name": "测试甲", "legacy_code_numeric": "222"},
            "S2": {"xlsx_name": "测试乙", "legacy_code_numeric": "22"},
        }
        file = {"recording_code": "22", "filename_abbr": "ABCD", "date": "20250616"}
        mentions = [
            {
                "current_subject_id": "S1",
                "target_date": "20250616",
                "mentioned_code": "222",
            }
        ]
        links = [
            {"current_subject_id": "S1", "date": "20250616", "filename_abbr": "ABCD"}
        ]
        aliases = {"S1": {"ABCD"}, "S2": {"EFGH"}}
        self.assertTrue(
            can_correct(file, "S1", subjects, mentions, links, aliases, {"S2"}, 1)
        )
        self.assertFalse(
            can_correct(file, "S1", subjects, [], links, aliases, {"S2"}, 1)
        )
        self.assertFalse(
            can_correct(file, "S1", subjects, mentions, [], aliases, {"S2"}, 1)
        )
        aliases["S2"].add("ABCD")
        self.assertFalse(
            can_correct(file, "S1", subjects, mentions, links, aliases, {"S2"}, 1)
        )

    def test_same_name_multiple_vas_rows_cannot_share_by_name(self):
        subjects = {
            "S1": {"xlsx_name": "测试甲", "legacy_code_numeric": "222"},
            "S2": {"xlsx_name": "测试甲", "legacy_code_numeric": "22"},
        }
        file = {"recording_code": "22", "filename_abbr": "ABCD", "date": "20250616"}
        self.assertFalse(
            can_correct(
                file, "S1", subjects, [], [], {"S1": {"ABCD"}, "S2": {"ABCD"}}, set(), 1
            )
        )


if __name__ == "__main__":
    unittest.main()
