from datetime import datetime, date
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from capsaicin.participant_matching import (
    infer_target_date,
    levenshtein,
    parse_participant_line,
)


class ParticipantMatchingTests(unittest.TestCase):
    def test_parse_number_name_and_group(self):
        parsed = parse_participant_line("Z335都含笑--44魏微b1")
        self.assertEqual(parsed["code_numeric"], "335")
        self.assertEqual(parsed["name"], "都含笑")
        self.assertEqual(parsed["mention_type"], "assigned_or_recorded")

    def test_strip_group_label_and_reservation(self):
        parsed = parse_participant_line("269王思雨健康2--（预）")
        self.assertEqual(parsed["name"], "王思雨")
        self.assertEqual(parsed["group"], "健康2")
        self.assertEqual(parsed["mention_type"], "reservation")

    def test_date_inference_and_stale_copied_date(self):
        when = datetime(2025, 6, 3, 17, 0)
        actual, basis = infer_target_date("明天（4月11日）", when)
        self.assertEqual(actual, date(2025, 6, 4))
        self.assertIn("stale", basis)
        actual, basis = infer_target_date("明天（6月4日）", when)
        self.assertEqual(actual, date(2025, 6, 4))
        self.assertEqual(basis, "explicit_month_day")

    def test_unicode_edit_distance_handles_one_character_typo(self):
        self.assertEqual(levenshtein("陈彦宏", "陈启宏"), 1)
        self.assertEqual(levenshtein("贺家宜", "贺家谊"), 1)

    def test_room_or_storage_chat_is_not_a_participant(self):
        self.assertIsNone(parse_participant_line("303抽屉"))
        self.assertIsNone(parse_participant_line("301角落里有没有我们的东西"))
        self.assertIsNone(parse_participant_line("122没来得及改名字"))


if __name__ == "__main__":
    unittest.main()
