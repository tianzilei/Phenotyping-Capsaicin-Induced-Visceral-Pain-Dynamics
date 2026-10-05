"""Synthetic checks for independent-validation boundary auditing."""

from __future__ import annotations
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_recent_electrophysiology_claims import audit, old_pseudonym


class IntegrityAuditTests(unittest.TestCase):
    def test_development_sample_does_not_become_independent(self):
        ecg = [
            dict(
                subject_id="S1",
                recording_stem="R",
                stage="E",
                status="RPEAK_AUTO_ACCEPTED",
            )
        ]
        sample = [
            dict(
                blinded_record_id=old_pseudonym(ecg[0]),
                source_stage="E",
                sampling_stratum="RPEAK_AUTO_ACCEPTED",
                source_path_sha256="known",
            )
        ]
        split = [dict(person_id="S1", pool="development")]
        exposure = [dict(eligibility_decision="")]
        result = audit(
            ecg, [dict(e08_alt_status="E08_ALT_ESTIMATED")], sample, split, exposure
        )
        self.assertEqual(
            result["historical_sampling_records_by_pool"], {"development": 1}
        )
        self.assertEqual(result["exposure_eligibility_decisions_recorded"], 0)
        self.assertTrue(result["historical_review_csv_exposes_cqs_stratum"])
        self.assertFalse(result["scientific_error_rates_estimable"])

    def test_unmatched_pseudonym_is_reported(self):
        result = audit([], [], [dict(blinded_record_id="EVAL_UNKNOWN")], [], [])
        self.assertEqual(result["historical_sampling_unmatched_ids"], 1)
        self.assertEqual(result["historical_sampling_records"], 1)


if __name__ == "__main__":
    unittest.main()
