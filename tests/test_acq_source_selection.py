import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from capsaicin.acq_source_selection import apply_acq_registry


class ACQSelection(unittest.TestCase):
    def test_shared_owner_and_alternative_record_excluded_without_identity_merge(self):
        rows = [
            dict(current_subject_id=s, path=p)
            for s, p in [
                ("SYN_SUBJECT002", "shared.acq"),
                ("SYN_SUBJECT010", "shared.acq"),
                ("SYN_SUBJECT002", "alternate.acq"),
            ]
        ]
        reg = {
            "decisions": [
                dict(
                    person_id=r["current_subject_id"],
                    path=r["path"],
                    sha256="hash",
                    selected=i == 0,
                )
                for i, r in enumerate(rows)
            ]
        }
        kept, audit = apply_acq_registry(rows, reg, lambda p: "hash")
        self.assertEqual(kept, [rows[0]])
        self.assertEqual(len(audit), 3)
        self.assertEqual(rows[1]["current_subject_id"], "SYN_SUBJECT010")

    def test_changed_bytes_and_unregistered_records_rejected(self):
        row = dict(current_subject_id="SYN_SUBJECT001", path="synthetic.acq")
        reg = {
            "decisions": [
                dict(
                    person_id="SYN_SUBJECT001",
                    path="synthetic.acq",
                    sha256="old",
                    selected=True,
                )
            ]
        }
        with self.assertRaises(ValueError):
            apply_acq_registry([row], reg, lambda p: "new")
        with self.assertRaises(ValueError):
            apply_acq_registry([dict(row, path="other.acq")], reg, lambda p: "old")

    def test_registry_cannot_keep_two_people_for_one_file(self):
        rows = [
            dict(current_subject_id=s, path="same.acq")
            for s in ["SYN_SUBJECT001", "SYN_SUBJECT002"]
        ]
        reg = {
            "decisions": [
                dict(
                    person_id=r["current_subject_id"],
                    path=r["path"],
                    sha256="h",
                    selected=True,
                )
                for r in rows
            ]
        }
        with self.assertRaises(ValueError):
            apply_acq_registry(rows, reg, lambda p: "h")
