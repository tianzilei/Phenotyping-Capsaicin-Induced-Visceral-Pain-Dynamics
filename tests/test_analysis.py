import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.analysis import observed_summaries, validate_execution_config
from capsaicin.contracts import ContractError


class AnalysisTests(unittest.TestCase):
    def test_auc_does_not_bridge_gap_or_invent_baseline(self):
        rows = [
            dict(
                subject_id="synthetic",
                time_min=t,
                vas=v,
                status="observed" if v is not None else "missing",
                termination_code="",
            )
            for t, v in [(1, 2), (2, None), (3, 6), (4, 8)]
        ]
        z = observed_summaries(rows)[0]
        self.assertEqual(z["observed_adjacent_auc"], 7)
        self.assertEqual(z["auc_covered_minutes"], 1)
        self.assertEqual(z["raw_mssd"], 4)

    def test_no_pairs_auc_undefined_and_zero_auc_retained(self):
        for values, expected in [([None, None], None), ([0, None], None), ([0, 0], 0)]:
            rows = [
                dict(
                    subject_id="synthetic",
                    time_min=t + 1,
                    vas=v,
                    status="missing" if v is None else "observed",
                    termination_code="",
                )
                for t, v in enumerate(values)
            ]
            self.assertEqual(
                observed_summaries(rows)[0]["observed_adjacent_auc"], expected
            )

    def test_draft_or_unsupported_estimator_cannot_execute(self):
        cfg = json.loads(
            (ROOT / "config/provisional_vas_v1.json").read_text(encoding="utf-8")
        )
        validate_execution_config(cfg)
        for section, key, value in [
            (None, "status", "draft_not_frozen"),
            ("fpca", "engine", "invented"),
            ("markov", "enabled", True),
            ("data", "vas_max", 100),
            ("gamm", "bootstrap_subjects", 0),
        ]:
            bad = copy.deepcopy(cfg)
            (bad if section is None else bad[section])[key] = value
            with self.assertRaises(ContractError):
                validate_execution_config(bad)
