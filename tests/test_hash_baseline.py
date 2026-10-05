"""Synthetic strictness checks for registered historical code evolution."""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from capsaicin.hash_baseline import HashBaseline, digest


class BaselineTests(unittest.TestCase):
    def test_only_registered_exact_code_transition_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = root / "code.py"
            mp = root / "run_manifest.json"
            ledger = root / "ledger.csv"
            settings = root / "active.json"
            code.write_text("old")
            old = digest(code)
            mp.write_text(json.dumps({"inputs_sha256": {str(code): old}}))
            code.write_text("current")
            row = dict(
                manifest=str(mp),
                manifest_sha256=digest(mp),
                field="inputs_sha256",
                name=str(code),
                expected_sha256=old,
                current_path=str(code),
                current_sha256=digest(code),
                status="current_code_or_document_version",
            )
            with ledger.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(row))
                w.writeheader()
                w.writerow(row)
            settings.write_text(
                json.dumps(
                    dict(
                        active=True,
                        historical_ledger=str(ledger),
                        historical_ledger_sha256=digest(ledger),
                    )
                )
            )
            b = HashBaseline(settings)
            self.assertEqual(
                b.check(mp, "inputs_sha256", str(code), old, code),
                "registered_historical_code_or_document_version",
            )
            with self.assertRaises(ValueError):
                b.check(mp, "outputs_sha256", str(code), old, code)
            code.write_text("later edit")
            with self.assertRaises(ValueError):
                b.check(mp, "inputs_sha256", str(code), old, code)
            code.write_text("current")
            mp.write_text("{}")
            with self.assertRaises(ValueError):
                b.check(mp, "inputs_sha256", str(code), old, code)
            ledger.write_text("corrupted")
            with self.assertRaises(ValueError):
                HashBaseline(settings).check(mp, "inputs_sha256", str(code), old, code)

    def test_no_baseline_never_accepts_changed_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "signal.csv"
            data.write_text("1,2")
            old = digest(data)
            b = HashBaseline(root / "absent")
            self.assertEqual(
                b.check(root / "run.json", "signals_sha256", str(data), old, data),
                "matched",
            )
            data.write_text("3,4")
            with self.assertRaises(ValueError):
                b.check(root / "run.json", "signals_sha256", str(data), old, data)

    def test_relocated_bytes_require_exact_archived_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "local.csv"
            data.write_text("unchanged")
            expected = digest(data)
            mp = root / "run.json"
            mp.write_text("{}")
            missing = root / "missing.csv"
            ledger = root / "ledger.csv"
            cp = root / "config.json"
            row = dict(
                manifest=str(mp),
                manifest_sha256=digest(mp),
                field="signals_sha256",
                name=str(missing),
                expected_sha256=expected,
                current_path=str(missing),
                current_sha256="",
                status="historical_bytes_available_at_other_path",
                matching_bytes_paths=json.dumps([str(data)]),
            )
            with ledger.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(row))
                w.writeheader()
                w.writerow(row)
            cp.write_text(
                json.dumps(
                    dict(
                        active=True,
                        historical_ledger=str(ledger),
                        historical_ledger_sha256=digest(ledger),
                    )
                )
            )
            b = HashBaseline(cp)
            self.assertEqual(
                b.check(mp, "signals_sha256", str(missing), expected, missing),
                "historical_bytes_verified_at_other_path",
            )
            data.write_text("changed")
            with self.assertRaises(ValueError):
                b.check(mp, "signals_sha256", str(missing), expected, missing)


if __name__ == "__main__":
    unittest.main()
