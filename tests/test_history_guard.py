"""History cleanup is exercised exclusively with temporary synthetic Git repos."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_public_history import verify_history


class HistoryGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Synthetic test")
        self.git("config", "user.email", "synthetic@example.invalid")
        (self.root / "docs").mkdir()
        (self.root / "docs/release_inventory.json").write_text(
            json.dumps({"aggregate_files": {}, "source_snapshot": {}})
        )
        (self.root / "README.md").write_text("Synthetic release fixture only.\n")
        self.commit()

    def git(self, *args, input=None):
        return subprocess.check_output(
            ["git", *args], cwd=self.root, input=input, stderr=subprocess.DEVNULL
        )

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-m", "Synthetic fixture")

    def test_clean_root_passes(self):
        result = verify_history(self.root)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["commits"], 1)
        self.assertEqual(result["unreachable_objects"], 0)

    def test_deleted_individual_file_still_rejected(self):
        path = self.root / "BaselineData.csv"
        path.write_text("ID,VAS\nSYN_ONLY,2\n")
        self.commit()
        path.unlink()
        self.commit()
        result = verify_history(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(
            any(item.get("file") == "BaselineData.csv" for item in result["failures"])
        )

    def test_unreachable_blob_rejected(self):
        self.git("hash-object", "-w", "--stdin", input=b"Synthetic discarded object\n")
        result = verify_history(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["unreachable_objects"], 1)

    def test_symlink_rejected(self):
        (self.root / "link.md").symlink_to("README.md")
        self.commit()
        result = verify_history(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(
            any(item.get("file") == "link.md" for item in result["failures"])
        )

    def test_shallow_history_rejected(self):
        head = self.git("rev-parse", "HEAD").decode().strip()
        (self.root / ".git/shallow").write_text(head + "\n")
        self.assertEqual(verify_history(self.root)["status"], "FAIL")

    def test_background_ref_change_rejected(self):
        original = subprocess.check_output
        changed = False

        def concurrent_git(args, **kwargs):
            nonlocal changed
            if args[1:2] == ["ls-tree"] and not changed:
                changed = True
                self.git("update-ref", "refs/heads/background", "HEAD")
            return original(args, **kwargs)

        with mock.patch(
            "verify_public_history.subprocess.check_output", side_effect=concurrent_git
        ):
            result = verify_history(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(
            any("changed during audit" in item["reason"] for item in result["failures"])
        )

    def test_tree_ref_cannot_bypass_commit_scan(self):
        self.git("update-ref", "refs/tags/synthetic-tree", "HEAD^{tree}")
        result = verify_history(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(
            any("auditable commit" in item["reason"] for item in result["failures"])
        )

    def test_detached_head_is_audited(self):
        self.git("checkout", "--detach")
        (self.root / "BaselineData.csv").write_text("ID,VAS\nSYN_ONLY,2\n")
        self.commit()
        result = verify_history(self.root)
        self.assertEqual(result["commits"], 2)
        self.assertTrue(
            any(item.get("file") == "BaselineData.csv" for item in result["failures"])
        )

    def test_historical_hash_change_rejected_after_restoration(self):
        path = self.root / "aggregate.csv"
        data = b"count\n10\n"
        path.write_bytes(data)
        (self.root / "docs/release_inventory.json").write_text(
            json.dumps(
                {
                    "aggregate_files": {
                        "aggregate.csv": {
                            "published_sha256": hashlib.sha256(data).hexdigest()
                        }
                    },
                    "source_snapshot": {},
                }
            )
        )
        self.commit()
        path.write_bytes(b"count\n11\n")
        self.commit()
        path.write_bytes(data)
        self.commit()
        result = verify_history(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(
            any(
                item.get("reason") == "Approved aggregate hash mismatch"
                for item in result["failures"]
            )
        )


if __name__ == "__main__":
    unittest.main()
