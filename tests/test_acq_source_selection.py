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
                dict(person_id=r["current_subject_id"], path=r["path"], selected=i == 0)
                for i, r in enumerate(rows)
            ]
        }
        kept, audit = apply_acq_registry(rows, reg)
        self.assertEqual(kept, [rows[0]])
        self.assertEqual(len(audit), 3)
        self.assertEqual(rows[1]["current_subject_id"], "SYN_SUBJECT010")

    def test_unregistered_records_and_duplicate_decisions_rejected(self):
        row = dict(current_subject_id="SYN_SUBJECT001", path="synthetic.acq")
        decision = dict(person_id="SYN_SUBJECT001", path="synthetic.acq", selected=True)
        with self.assertRaises(ValueError):
            apply_acq_registry([dict(row, path="other.acq")], {"decisions": [decision]})
        with self.assertRaises(ValueError):
            apply_acq_registry([row], {"decisions": [decision, decision]})

    def test_registry_cannot_keep_two_people_for_one_file(self):
        rows = [
            dict(current_subject_id=s, path="same.acq")
            for s in ["SYN_SUBJECT001", "SYN_SUBJECT002"]
        ]
        reg = {
            "decisions": [
                dict(person_id=r["current_subject_id"], path=r["path"], selected=True)
                for r in rows
            ]
        }
        with self.assertRaises(ValueError):
            apply_acq_registry(rows, reg)
