import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.stopping import (
    audit_stopping,
    stopping_distribution,
    bounded_means,
    area_bounds,
    observed_bootstrap,
)


def series(sid, tokens):
    rows = []
    code = ""
    for t, x in enumerate(tokens, 1):
        if x in ("E", "T"):
            code = x
            status = "termination_" + x
            v = None
        elif x is None:
            status = "post_termination" if code else "missing"
            v = None
        else:
            status = "observed"
            v = float(x)
        rows.append(
            dict(
                subject_id=sid,
                time_min=t,
                vas=v,
                status=status,
                termination_code=code,
                raw_token=str(x),
            )
        )
    return rows


class StoppingTests(unittest.TestCase):
    def test_processed_E_does_not_require_preceding_zeros(self):
        rows = series("processed", [3, 2, "E", None]) + series(
            "pending", [0, 0, "E", None]
        )
        result = {r["subject_id"]: r for r in audit_stopping(rows, processed_E=True)}
        self.assertEqual(
            result["processed"]["E_recorded_support"],
            "existing_E_processed_no_preceding_zeros_required",
        )
        self.assertEqual(
            result["pending"]["E_recorded_support"], "remaining_uncoded_zero_pair"
        )

    def test_E_support_requires_actual_adjacent_zero_pair(self):
        rows = (
            series("two", [0, 0, "E", None])
            + series("gap", [0, None, "E", None])
            + series("nonzero", [1, 0, "E", None])
        )
        before = copy.deepcopy(rows)
        result = {x["subject_id"]: x for x in audit_stopping(rows)}
        self.assertEqual(
            result["two"]["E_recorded_support"], "two_preceding_recorded_zeros"
        )
        self.assertEqual(
            result["gap"]["E_recorded_support"], "preceding_numeric_window_unavailable"
        )
        self.assertEqual(
            result["nonzero"]["E_recorded_support"],
            "not_two_preceding_recorded_zeros_requires_review",
        )
        self.assertEqual(result["gap"]["n_observed_adjacent_zero_pairs"], 0)
        self.assertIsNone(result["two"]["verified_event_time_min"])
        self.assertEqual(rows, before)

    def test_T_counted_once_no_exclusion_or_individual_reason_inference(self):
        rows = series("a", [9, "T", "T", None]) + series("b", [0, 0, "E", None])
        audit = audit_stopping(rows)
        d = stopping_distribution(audit, [1, 2, 3, 4])
        self.assertEqual(audit[0]["n_observed"], 1)
        self.assertFalse(audit[0]["individual_stop_reason_verified"])
        self.assertEqual(d[-1]["n_T_by_minute"], 1)
        self.assertEqual(d[-1]["fraction_E_by_minute"], 0.5)
        self.assertEqual(sum(r["n_first_T"] for r in d), 1)

    def test_E_does_not_impute_zeros_and_bounds_decompose(self):
        rows = (
            series("a", [0, "E", None])
            + series("b", [8, "T", None])
            + series("c", [4, None, 4])
        )
        before = copy.deepcopy(rows)
        b = bounded_means(rows, [1, 2, 3], 0, 10)
        self.assertEqual(b[0]["cohort_mean_lower"], 4)
        self.assertEqual(b[0]["cohort_mean_upper"], 4)
        self.assertEqual(b[1]["cohort_mean_lower"], 0)
        self.assertEqual(b[1]["cohort_mean_upper"], 10)
        self.assertEqual(b[1]["n_unobserved_E"], 1)
        for r in b:
            self.assertAlmostEqual(
                r["cohort_mean_upper"] - r["cohort_mean_lower"],
                r["width_due_to_E"]
                + r["width_due_to_T"]
                + r["width_due_to_other_missing"],
            )
        a = area_bounds(b)
        self.assertAlmostEqual(a["candidate_mean_auc_lower"], 8 / 3)
        self.assertAlmostEqual(a["candidate_mean_auc_upper"], 16)
        self.assertEqual(rows, before)

    def test_all_missing_bounds_and_bootstrap_failures_explicit(self):
        rows = series("a", [None, None, None])
        b = bounded_means(rows, [1, 2, 3], 0, 10)
        self.assertEqual(area_bounds(b)["candidate_mean_auc_upper"], 20)
        out = observed_bootstrap(rows, [1, 2, 3], 20, 123)
        self.assertTrue(
            all(
                r["bootstrap_valid"] == 0 and r["bootstrap_pointwise_lower"] is None
                for r in out
            )
        )

    def test_subject_bootstrap_repeatable_and_does_not_create_unobserved_values(self):
        rows = series("a", [1, 2, 3]) + series("b", [1, 2, 3])
        a = observed_bootstrap(rows, [1, 2, 3], 50, 123)
        self.assertEqual(a, observed_bootstrap(rows, [1, 2, 3], 50, 123))
        for t, row in enumerate(a, 1):
            self.assertEqual(row["bootstrap_pointwise_lower"], t)
            self.assertEqual(row["bootstrap_pointwise_upper"], t)
            self.assertEqual(row["bootstrap_valid"], 50)
