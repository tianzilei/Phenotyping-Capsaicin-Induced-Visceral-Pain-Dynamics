"""Synthetic date-ranking checks; never use participant fixtures."""

import sys
import tempfile
import unittest
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from capsaicin.fnirs_source_selection import (
    choose_latest,
    measured_date,
    adjudicate_mapping,
    sha,
)


class SourceSelectionTests(unittest.TestCase):
    def test_acquisition_time_including_same_day_order(self):
        rows = [
            dict(measured_date="2025-01-01T12:00:00", sha256="old"),
            dict(measured_date="2025-01-01T12:01:00", sha256="new"),
        ]
        self.assertEqual(choose_latest(rows)["sha256"], "new")
        self.assertEqual(choose_latest(rows[::-1])["sha256"], "new")

    def test_nonidentical_tie_is_not_arbitrarily_selected(self):
        with self.assertRaises(ValueError):
            choose_latest(
                [dict(measured_date="2025-01-01", sha256=s) for s in ["a", "b"]]
            )
        with self.assertRaises(ValueError):
            choose_latest([])

    def test_header_date_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "synthetic.txt"
            p.write_text("Measured Date\t2025/01/02 03:04:05\n", encoding="utf-8")
            self.assertEqual(measured_date(p).isoformat(), "2025-01-02T03:04:05")
            p.write_text("Missing\tdate\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                measured_date(p)

    def test_alias_not_double_counted_and_changed_signal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "old.txt"
            b = root / "latest.txt"
            a.write_text("old")
            b.write_text("new")
            candidates = [
                dict(local_path=str(p), sha256=sha(p), measured_date="2025-01-01")
                for p in [a, b]
            ]
            registry = root / "registry.json"
            pointer = root / "active.json"
            decisions = {
                sid: dict(
                    candidates=candidates, selected=candidates[1], analysis_status=state
                )
                for sid, state in [
                    ("S1", "accepted_unique_owner"),
                    ("S2", "alias_of_same_participant_do_not_count_twice"),
                ]
            }
            registry.write_text(json.dumps(dict(decisions=decisions)))
            pointer.write_text(
                json.dumps(
                    dict(
                        active=True,
                        registry=str(registry),
                        registry_sha256=sha(registry),
                    )
                )
            )
            rows = [
                dict(current_subject_id=sid, path=str(p))
                for sid in ["S1", "S2"]
                for p in [a, b]
            ]
            accepted, audit, evidence = adjudicate_mapping(rows, pointer)
            self.assertEqual(accepted, [dict(current_subject_id="S1", path=str(b))])
            self.assertEqual(len(audit), 4)
            frozen = json.loads(pointer.read_text())
            accepted_frozen, _, _ = adjudicate_mapping(rows, frozen)
            self.assertEqual(accepted_frozen, accepted)
            b.write_text("mutated")
            with self.assertRaises(ValueError):
                adjudicate_mapping(rows, pointer)

    def test_shared_owner_and_hashed_additional_link(self):
        from capsaicin.data_locations import path_key

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "shared.txt"
            p.write_text("synthetic")
            q = root / "added.txt"
            q.write_text("synthetic added")
            c = dict(local_path=str(q), sha256=sha(q), measured_date="2025-01-01")
            reg = dict(
                decisions={
                    "S3": dict(
                        candidates=[c],
                        selected=c,
                        analysis_status="accepted_unique_owner",
                    )
                },
                file_owners={path_key(p): dict(owner="S1", sha256=sha(p))},
                additional_mapping_rows=[dict(current_subject_id="S3", path=str(q))],
            )
            rp = root / "reg.json"
            rp.write_text(json.dumps(reg))
            ptr = dict(active=True, registry=str(rp), registry_sha256=sha(rp))
            rows = [dict(current_subject_id=s, path=str(p)) for s in ["S1", "S2"]]
            selected, _, _ = adjudicate_mapping(rows, ptr)
            self.assertEqual([r["current_subject_id"] for r in selected], ["S1", "S3"])
            again, _, _ = adjudicate_mapping(selected, ptr)
            self.assertEqual(again, selected)
            q.write_text("changed")
            with self.assertRaises(ValueError):
                adjudicate_mapping(rows, ptr)


if __name__ == "__main__":
    unittest.main()
