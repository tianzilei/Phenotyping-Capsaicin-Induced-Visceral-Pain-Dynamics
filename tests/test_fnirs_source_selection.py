"""Synthetic explicit-path selection and ownership contracts."""

from pathlib import Path
import json
import tempfile
import unittest
from capsaicin.fnirs_source_selection import (
    choose_latest,
    measured_date,
    adjudicate_mapping,
)


class SourceSelectionTests(unittest.TestCase):
    def test_latest_and_ambiguous_tie(self):
        rows = [
            dict(local_path="synthetic_old", measured_date="2025-01-01T12:00:00"),
            dict(local_path="synthetic_new", measured_date="2025-01-01T12:01:00"),
        ]
        self.assertEqual(choose_latest(rows)["local_path"], "synthetic_new")
        with self.assertRaises(ValueError):
            choose_latest([dict(r, measured_date="2025-01-01") for r in rows])
        with self.assertRaises(ValueError):
            choose_latest([])

    def test_header_date_and_explicit_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root / "synthetic.txt"
            p.write_text("Measured Date\t2025/01/02 03:04:05\n")
            self.assertEqual(measured_date(p).isoformat(), "2025-01-02T03:04:05")
            candidate = dict(local_path=str(p), measured_date="2025-01-02T03:04:05")
            decisions = {
                sid: dict(
                    candidates=[candidate], selected=candidate, analysis_status=status
                )
                for sid, status in [
                    ("SYN1", "accepted_unique_owner"),
                    ("SYN2", "alias_do_not_count_twice"),
                ]
            }
            registry = root / "registry.json"
            registry.write_text(json.dumps(dict(decisions=decisions)))
            pointer = dict(active=True, registry=str(registry))
            rows = [dict(current_subject_id=sid, path=str(p)) for sid in decisions]
            kept, audit, _ = adjudicate_mapping(rows, pointer)
            self.assertEqual(kept, [rows[0]])
            self.assertEqual(len(audit), 2)
            with self.assertRaises(ValueError):
                adjudicate_mapping(
                    [dict(rows[0], path=str(root / "unknown.txt"))], pointer
                )
