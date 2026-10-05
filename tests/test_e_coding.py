import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from capsaicin.e_coding import recode_pending_zeros, recode_connected_zeros
from capsaicin.contracts import ContractError


class ECodingTests(unittest.TestCase):
    def test_connected_odd_run_and_single_zero_idempotent(self):
        for count in [1, 2, 3, 4, 5]:
            row = {
                "ID": "synthetic",
                **{
                    f"VAS_{t}min": ("2" if t < 6 - count else "0" if t < 6 else "E")
                    for t in range(1, 21)
                },
            }
            before = copy.deepcopy(row)
            out, changes = recode_connected_zeros([row])
            self.assertEqual(len(changes), count)
            self.assertEqual(row, before)
            again, extra = recode_connected_zeros(out)
            self.assertEqual(again, out)
            self.assertFalse(extra)

    def test_does_not_cross_gap_or_nonzero_or_recode_T_or_no_marker(self):
        for barrier in ["", "NA", "1"]:
            row = {
                "ID": "synthetic",
                **{f"VAS_{t}min": "E" if t >= 6 else "0" for t in range(1, 21)},
            }
            row["VAS_4min"] = barrier
            out, changes = recode_connected_zeros([row])
            self.assertEqual([r["time_min"] for r in changes], [5])
            self.assertEqual(out[0]["VAS_3min"], "0")
        for marker in ["T", "0"]:
            row = {
                "ID": "synthetic",
                **{f"VAS_{t}min": marker if t >= 6 else "0" for t in range(1, 21)},
            }
            self.assertEqual(recode_connected_zeros([row]), ([row], []))

    def fixture(self):
        row = {
            "ID": "synthetic",
            "note": "unchanged",
            **{f"VAS_{t}min": "E" if t >= 6 else "2" for t in range(1, 21)},
        }
        row.update(VAS_1min="0", VAS_4min="0.0", VAS_5min="0")
        return (
            [row],
            [
                dict(
                    subject_id="synthetic",
                    first_marker_min=6,
                    E_recorded_support="two_preceding_recorded_zeros",
                )
            ],
            dict(expected_subjects=1, expected_changed_cells=2, version="synthetic"),
        )

    def test_only_authorized_pair_changed_source_preserved(self):
        rows, audit, cfg = self.fixture()
        before = copy.deepcopy(rows)
        output, changes = recode_pending_zeros(rows, audit, cfg)
        self.assertEqual(rows, before)
        self.assertEqual(output[0]["VAS_1min"], "0")
        self.assertEqual([r["field"] for r in changes], ["VAS_4min", "VAS_5min"])
        self.assertEqual(output[0]["note"], "unchanged")
        self.assertEqual(output[0]["VAS_6min"], "E")

    def test_changed_source_rejected(self):
        for field, value in [("VAS_4min", "1"), ("VAS_6min", "T"), ("VAS_3min", "E")]:
            rows, audit, cfg = self.fixture()
            rows[0][field] = value
            with self.assertRaises(ContractError):
                recode_pending_zeros(rows, audit, cfg)

    def test_wrong_count_and_repeat_application_rejected(self):
        rows, audit, cfg = self.fixture()
        with self.assertRaises(ContractError):
            recode_pending_zeros(rows, [], cfg)
        output, _ = recode_pending_zeros(rows, audit, cfg)
        with self.assertRaises(ContractError):
            recode_pending_zeros(output, audit, cfg)
