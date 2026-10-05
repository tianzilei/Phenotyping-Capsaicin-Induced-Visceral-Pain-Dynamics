"""Only synthetic records exercise the restricted export contract."""

import csv
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.privacy import PrivacyError, deidentify, read_table


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.csv"
        self.source.write_text(
            "ID,VAS_1min,VAS_2min,VAS_3min,VAS_10min,Age,Additional_symptoms,ACQ_CNP_files\n"
            "SYN_A,0,,E,NA,21,synthetic comment,/private/record.acq\n"
            "SYN_B,9,T,,N/A,22,,\n",
            encoding="utf-8",
        )
        self.spec = dict(
            input=str(self.source),
            output_name="baseline.csv",
            primary_id="ID",
            id_columns=["ID"],
            keep_columns=["ID", "VAS_1min", "VAS_2min", "VAS_3min", "VAS_10min", "Age"],
        )

    def test_exact_values_aliases_linkage_and_permissions(self):
        linked = self.root / "linked.csv"
        linked.write_text(
            "person_id,value\nSYN_ALIAS,3.000\nSYN_B,\n", encoding="utf-8"
        )
        spec = dict(
            input=str(linked),
            output_name="derived.csv",
            id_columns=["person_id"],
            keep_columns=["person_id", "value"],
        )
        before = self.source.read_bytes()
        out = self.root / "release"
        result = deidentify([self.spec, spec], out, {"SYN_ALIAS": "SYN_A"})
        _, mapped = read_table(out / "identity_mapping_PRIVATE.csv")
        ids = {r["source_id"]: r["pseudonym"] for r in mapped}
        self.assertEqual(ids["SYN_A"], ids["SYN_ALIAS"])
        self.assertNotEqual(ids["SYN_A"], ids["SYN_B"])
        self.assertRegex(ids["SYN_A"], r"^P_[0-9a-f]{24}$")
        fields, rows = read_table(out / "baseline.csv")
        row = next(r for r in rows if r["ID"] == ids["SYN_A"])
        self.assertEqual([row[k] for k in fields[1:]], ["0", "", "E", "NA", "21"])
        self.assertNotIn("Additional_symptoms", fields)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(result["canonical_people"], 2)
        self.assertEqual(os.stat(out).st_mode & 0o777, 0o700)
        self.assertEqual(
            os.stat(out / "identity_mapping_PRIVATE.csv").st_mode & 0o777, 0o600
        )

    def test_refuses_overwrite_and_git_checkout(self):
        out = self.root / "existing"
        out.mkdir()
        with self.assertRaises(PrivacyError):
            deidentify([self.spec], out)
        checkout = self.root / "checkout"
        (checkout / ".git").mkdir(parents=True)
        for dest in [checkout / "data", ROOT / "private" / "output"]:
            with self.assertRaises(PrivacyError):
                deidentify([self.spec], dest)

    def test_unknown_foreign_key_and_cyclic_aliases_fail_without_output(self):
        linked = self.root / "linked.csv"
        linked.write_text("subject_id,value\nSYN_UNKNOWN,1\n")
        spec = dict(
            input=str(linked),
            output_name="linked.csv",
            id_columns=["subject_id"],
            keep_columns=["subject_id", "value"],
        )
        for aliases, tables in [
            ({}, [self.spec, spec]),
            ({"SYN_A": "SYN_B", "SYN_B": "SYN_A"}, [self.spec]),
        ]:
            with self.assertRaises(PrivacyError):
                deidentify(tables, self.root / "bad", aliases)
            self.assertFalse((self.root / "bad").exists())

    def test_blocks_identifying_columns_paths_and_undeclared_identifiers(self):
        for field in ["Additional_symptoms", "ACQ_CNP_files"]:
            with self.assertRaises(PrivacyError):
                deidentify(
                    [dict(self.spec, keep_columns=self.spec["keep_columns"] + [field])],
                    self.root / "bad",
                )
        spec = dict(self.spec, id_columns=[], primary_id=None)
        with self.assertRaises(PrivacyError):
            deidentify([spec], self.root / "bad")
        self.source.write_text("ID,value\nSYN_A,/private/synthetic/record.acq\n")
        with self.assertRaises(PrivacyError):
            deidentify(
                [dict(self.spec, keep_columns=["ID", "value"])], self.root / "bad"
            )

    def test_malformed_headers_rows_and_traversal_fail(self):
        for text in [
            "ID,ID\nSYN_A,SYN_A\n",
            "ID,value\nSYN_A\n",
            "ID,value\nSYN_A,1,extra\n",
        ]:
            self.source.write_text(text)
            with self.assertRaises(PrivacyError):
                read_table(self.source)
        with self.assertRaises(PrivacyError):
            deidentify(
                [dict(self.spec, output_name="../escape.csv")], self.root / "bad"
            )


if __name__ == "__main__":
    unittest.main()
