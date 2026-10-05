"""Synthetic migration tests: exact aliases, missingness and copy integrity."""

import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.data_locations import DataLocator, path_key

spec = importlib.util.spec_from_file_location(
    "migration", ROOT / "scripts/migrate_data_to_bids.py"
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class MigrationTests(unittest.TestCase):
    def test_private_location_environment_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            settings = root / "locations.json"
            explicit = root / "explicit.json"
            settings.write_text('{"active":false,"synthetic":true}')
            explicit.write_text('{"active":false,"synthetic":"explicit"}')
            with patch.dict("os.environ", {"CAPSAICIN_DATA_LOCATIONS": str(settings)}):
                self.assertTrue(DataLocator().settings["synthetic"])
                self.assertEqual(
                    DataLocator(explicit).settings["synthetic"], "explicit"
                )

    def test_behavior_preserves_markers_missing_and_minutes(self):
        source = {
            "VAS_1min": "0",
            "VAS_2min": "3",
            "VAS_3min": "",
            "VAS_4min": "E",
            "VAS_5min": "T",
        }
        rows = migration.behavior_rows(source)
        self.assertEqual([r["time_min"] for r in rows], list(range(1, 21)))
        self.assertEqual(rows[0]["vas"], "0")
        self.assertEqual(rows[2]["observation_status"], "missing")
        self.assertEqual([r["original_token"] for r in rows[3:5]], ["E", "T"])
        self.assertEqual([r["vas"] for r in rows[3:5]], ["n/a", "n/a"])
        self.assertEqual(source["VAS_3min"], "")
        with self.assertRaises(ValueError):
            migration.behavior_rows({"VAS_1min": "NaN999"})
        with self.assertRaises(ValueError):
            migration.behavior_rows({"VAS_1min": "11"})

    def test_copy_hash_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = root / "a"
            b = root / "nested/b"
            a.write_bytes(b"\x00synthetic\xff\r\n")
            digest, size = migration.copy_verified(a, b)
            self.assertEqual(digest, migration.sha(b))
            self.assertEqual(size, len(a.read_bytes()))
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(migration.copy_verified(a, b), (digest, size))
            b.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                migration.copy_verified(a, b)
            self.assertEqual(b.read_bytes(), b"changed")

    def test_same_basename_exact_aliases_and_no_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = root / "a.txt"
            b = root / "b.txt"
            a.write_text("first")
            b.write_text("second")
            index = root / "index.json"
            settings = root / "locations.json"
            index.write_text(
                json.dumps(
                    {
                        path_key("F:/folder1/signal.txt"): str(a),
                        path_key("F:/folder2/signal.txt"): str(b),
                    }
                )
            )
            settings.write_text(json.dumps(dict(active=True, path_index=str(index))))
            loc = DataLocator(settings)
            self.assertEqual(loc.resolve("f:\\FOLDER1\\signal.txt"), a)
            self.assertEqual(loc.resolve("F:/folder2/signal.txt"), b)
            with self.assertRaises(FileNotFoundError):
                loc.resolve("F:/folder3/signal.txt")
            a.unlink()
            with self.assertRaises(FileNotFoundError):
                loc.resolve("F:/folder1/signal.txt")

    def test_no_settings_keeps_local_paths_and_explicit_config_overlay(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            config = root / "original.json"
            overlay = root / "local.json"
            settings = root / "settings.json"
            config.write_text("{}")
            overlay.write_text('{"synthetic":true}')
            self.assertEqual(DataLocator(root / "absent").resolve(config), config)
            settings.write_text(
                json.dumps(dict(config_overrides={path_key(config): str(overlay)}))
            )
            self.assertEqual(DataLocator(settings).config_path(config), overlay)
            self.assertEqual(config.read_text(), "{}")


if __name__ == "__main__":
    unittest.main()
