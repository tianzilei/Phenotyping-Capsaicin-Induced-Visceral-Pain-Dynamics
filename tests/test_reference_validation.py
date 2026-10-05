import unittest
from capsaicin.reference_validation import (
    reference_contract,
    match_events,
    reference_nn_hrv,
    named_clock_fit,
    clinical_label_contract,
)


class ReferenceValidationTests(unittest.TestCase):
    def test_missing_reference_is_pending(self):
        self.assertFalse(reference_contract({}, "abc")["admissible_contract"])

    def test_source_and_human_attestation_required(self):
        row = dict(
            source_sha256="a",
            reviewer_id="synthetic",
            independence_attestation="independent_human_attested",
            adjudication_id="synthetic",
            annotation_version="fixture",
        )
        self.assertTrue(reference_contract(row, "a")["admissible_contract"])
        self.assertFalse(reference_contract(row, "b")["admissible_contract"])
        row["independence_attestation"] = "algorithm_generated"
        self.assertFalse(reference_contract(row, "a")["admissible_contract"])

    def test_match_is_one_to_one_and_minimizes_error(self):
        r = match_events([1.0, 2.0], [0.90, 1.01, 2.02], 0.15)
        self.assertEqual(r["pairs"], [(0, 1), (1, 2)])
        self.assertEqual((r["TP"], r["FP"], r["FN"]), (2, 1, 0))

    def test_match_empty_and_duplicate(self):
        self.assertIsNone(match_events([], [], 0.15)["sensitivity"])
        with self.assertRaises(ValueError):
            match_events([1, 1], [1], 0.1)

    def test_abnormal_beat_does_not_join_normal_intervals(self):
        beats = [
            dict(time_s=t, beat_type=c)
            for t, c in [
                (0, "normal"),
                (1, "normal"),
                (2, "abnormal"),
                (4, "normal"),
                (5, "normal"),
            ]
        ]
        r = reference_nn_hrv(beats, 0, 6)
        self.assertEqual(r["nn_count"], 2)
        self.assertIsNone(r["rmssd_ms"])

    def test_unreadable_gap_does_not_bridge_changes(self):
        b = [dict(time_s=t, beat_type="normal") for t in [0, 1, 2.1, 3.1, 4.3]]
        r = reference_nn_hrv(b, 0, 5, [(1.5, 2.5)])
        self.assertEqual(r["nn_count"], 2)
        self.assertEqual(r["adjacent_nn_change_count"], 0)

    def test_window_end_is_excluded(self):
        b = [dict(time_s=t, beat_type="normal") for t in [0, 1, 2]]
        r = reference_nn_hrv(b, 0, 2)
        self.assertEqual(r["nn_count"], 1)

    def test_known_rmssd(self):
        b = [dict(time_s=t, beat_type="normal") for t in [0, 1, 2.1, 3.1]]
        self.assertAlmostEqual(reference_nn_hrv(b, 0, 4)["rmssd_ms"], 100.0)

    def test_named_drift_has_holdout(self):
        a = [
            dict(event_identity=str(i), acq_s=x, hb_s=2 + 1.001 * x, role=role)
            for i, (x, role) in enumerate([(0, "fit"), (100, "fit"), (50, "holdout")])
        ]
        r = named_clock_fit(a)
        self.assertAlmostEqual(r["drift_ppm"], 1000)
        self.assertAlmostEqual(r["max_abs_holdout_error_s"], 0)
        self.assertEqual(
            named_clock_fit(a[:2])["status"], "insufficient_named_anchor_support"
        )

    def test_cluster_labels_are_not_clinical_reference(self):
        row = dict(
            subject_id="fixture",
            clinical_target="fixture",
            reference_label="cluster_1",
            assessor_id="fixture",
            assessment_time="fixture",
            reference_source="clustering",
            independent_of_trajectory="no",
        )
        self.assertEqual(
            clinical_label_contract([row])["status"],
            "pending_independent_clinical_reference",
        )

    def test_empty_clinical_reference(self):
        self.assertEqual(clinical_label_contract([])["subjects"], 0)
