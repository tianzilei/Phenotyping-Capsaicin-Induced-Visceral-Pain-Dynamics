import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_fnirs_variable_length_roi import parse_channel_groups


class FnirsRoiParserTests(unittest.TestCase):
    def test_shimadzu_triplet_header_maps_42_channels(self):
        line = ["Time", "Task", "Mark", "Count"] + [
            f"ch-{i}" for i in range(1, 43) for _ in range(3)
        ]
        groups = parse_channel_groups(line)
        self.assertEqual(len(groups), 42)
        self.assertEqual(groups[0], ("ch-1", 4))
        self.assertEqual(groups[-1], ("ch-42", 127))

    def test_triplet_mismatch_rejected(self):
        line = ["Time", "Task", "Mark", "Count", "ch-1", "ch-2", "ch-1"]
        with self.assertRaisesRegex(ValueError, "triplet"):
            parse_channel_groups(line)
