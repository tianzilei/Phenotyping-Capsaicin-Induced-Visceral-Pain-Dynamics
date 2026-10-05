"""Synthetic regressions for accepted mapping provenance and unknown dates."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from capsaicin.reanalysis import source_mapping_admission, normalize_source_mapping_row
from capsaicin.reanalysis import acquisition_date_status as date_status


class AdmissionV2(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(
            (ROOT / "config/source_mapping_admission_20260927_v2.json").read_text()
        )
        self.row = dict(
            current_subject_id="SYN_SUBJECT001",
            path="synthetic/x.acq",
            filename="x.acq",
            stage="E",
            match_status="",
        )

    def test_supported_link_and_explicit_rejection(self):
        row = dict(
            self.row,
            supported="True",
            rule_version="enc_matching_v3",
            basis="source_code_and_reviewed_alias",
        )
        self.assertTrue(source_mapping_admission(row, self.cfg)[0])
        for delta in [
            dict(supported="False"),
            dict(rule_version="unknown"),
            dict(basis="unique_abbreviation_other_code_or_missing_code"),
            dict(match_status="unresolved"),
            dict(filename="._x.acq"),
            dict(stage="P"),
        ]:
            self.assertFalse(source_mapping_admission(dict(row, **delta), self.cfg)[0])
        self.assertFalse(source_mapping_admission(self.row, self.cfg)[0])

    def test_log_and_clock_evidence_required(self):
        row = dict(
            self.row,
            basis="exact_log_participant_actual_date_and_existing_identity_anchor",
            evidence_log_path="synthetic/log.csv",
            evidence_log_sha256="a" * 64,
        )
        self.assertTrue(source_mapping_admission(row, self.cfg)[0])
        self.assertFalse(
            source_mapping_admission(dict(row, evidence_log_sha256=""), self.cfg)[0]
        )
        row = dict(
            self.row,
            basis="accepted_chat_log_clock_rest_anchor",
            chat_message_keys="synthetic",
            log_interval_evidence="synthetic",
            device_timestamps="synthetic",
        )
        self.assertTrue(source_mapping_admission(row, self.cfg)[0])
        self.assertFalse(
            source_mapping_admission(dict(row, device_timestamps=""), self.cfg)[0]
        )

    def test_correction_must_target_row_subject(self):
        row = dict(
            self.row,
            basis="exact_chat_date_source_name_cross_device_code_typo",
            chat_date_match="True",
            abbreviation_match="True",
            chat_message_keys="synthetic",
            corrected_subject_id="SYN_SUBJECT001",
        )
        self.assertTrue(source_mapping_admission(row, self.cfg)[0])
        self.assertFalse(
            source_mapping_admission(
                dict(row, corrected_subject_id="SYN_SUBJECT002"), self.cfg
            )[0]
        )

    def test_extension_recovery_does_not_modify_source(self):
        row = dict(self.row, filename="x.ACQ", extension="")
        self.assertEqual(normalize_source_mapping_row(row)["extension"], ".acq")
        self.assertEqual(row["extension"], "")

    def test_unknown_dates_never_become_mismatches(self):
        self.assertEqual(
            date_status([dict(same_date=None)]), "unknown_acquisition_date"
        )
        self.assertEqual(date_status([dict(same_date=False)]), "different_dates_all")
        self.assertEqual(date_status([dict(same_date=True)]), "same_date_all")
        self.assertEqual(date_status([]), "no_admitted_Hb")


if __name__ == "__main__":
    unittest.main()
