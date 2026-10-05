"""Synthetic leak examples exercise release rejection; no real records."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_public_release import content_issue


class ReleaseGuardTests(unittest.TestCase):
    def test_unapproved_csv_and_individual_headers_rejected(self):
        self.assertIsNotNone(content_issue("data/new.csv", b"x\n1\n", {}, set()))
        for field in [
            "ID",
            "person_id",
            "subject_id",
            "participant_id",
            "source_subject",
            "source_id",
            "ACQ_CNP_files",
        ]:
            data = (field + ",value\nSYN_ONLY,1\n").encode()
            self.assertIsNotNone(
                content_issue("data/table.csv", data, {}, {"data/table.csv"})
            )

    def test_only_explicit_synthetic_fixture_and_empty_schemas_allowed(self):
        name = "tests/fixtures/synthetic_vas.csv"
        self.assertIsNone(content_issue(name, b"ID,VAS_1min\nSYN_A,E\n", {}, {name}))
        self.assertIsNotNone(
            content_issue(name, b"ID,VAS_1min\nOTHER_A,E\n", {}, {name})
        )
        name = "schemas/subjects.template.csv"
        self.assertIsNone(content_issue(name, b"subject_id\n", {}, {name}))
        self.assertIsNotNone(content_issue(name, b"subject_id\nSYN_A\n", {}, {name}))

    def test_private_artifacts_and_changed_aggregate_rejected(self):
        for name in [
            "BaselineData.csv",
            "results_private.csv",
            "record.acq",
            "private/x.json",
            "._file.py",
        ]:
            self.assertIsNotNone(content_issue(name, b"", {}, {name}))
        name = "data/aggregate.csv"
        expected = {name: {"published_sha256": "0" * 64}}
        self.assertIsNotNone(content_issue(name, b"count\n2\n", expected, {name}))

    def test_personal_path_rejected_without_flagging_detector_pattern(self):
        leak = ("/" + "Users/example_owner/private/record.csv").encode()
        self.assertIsNotNone(content_issue("docs/test.md", leak, {}, set()))
        code = (ROOT / "scripts/verify_public_release.py").read_bytes()
        self.assertIsNone(
            content_issue("scripts/verify_public_release.py", code, {}, set())
        )

    def test_credentials_rejected_in_yaml_shell_and_extensionless_text(self):
        secrets = [
            ("github_" + "pat_" + "A" * 40).encode(),
            ("gh" + "p_" + "B" * 36).encode(),
            ("-----BEGIN " + "OPENSSH PRIVATE KEY-----").encode(),
            ("https" + "://synthetic" + ":" + "placeholder@example.invalid/").encode(),
        ]
        for name in [
            ".github/workflows/test.yml",
            "scripts/test.sh",
            "credential_blob",
        ]:
            for data in secrets:
                self.assertIsNotNone(content_issue(name, data, {}, set()))

    def test_local_credential_files_rejected(self):
        for name in [".env", ".netrc", "config/hosts.yml", "hosts.yaml"]:
            self.assertIsNotNone(content_issue(name, b"", {}, set()))


if __name__ == "__main__":
    unittest.main()
