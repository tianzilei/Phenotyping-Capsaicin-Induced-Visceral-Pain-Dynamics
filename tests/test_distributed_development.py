"""Synthetic fixtures for logical RNG and durable distributed checkpoints."""

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from capsaicin.distributed_development import digest, execute, generate

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "development_driver", ROOT / "scripts/run_dask_derivative_development.py"
)
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


class DistributedDevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(
            (ROOT / "config/dask_derivative_development_20261003_v1.json").read_text()
        )
        self.cell = self.config["cells"][0]

    def test_seed_independent_of_execution_order_and_stage_separated(self):
        a = generate(self.config, self.cell, "smoke", 0)
        generate(self.config, self.cell, "smoke", 4)
        b = generate(self.config, self.cell, "smoke", 0)
        self.assertEqual(a["input_sha256"], b["input_sha256"])
        self.assertTrue(np.array_equal(a["values"], b["values"]))
        c = generate(self.config, self.cell, "development", 0)
        self.assertNotEqual(a["input_sha256"], c["input_sha256"])

    def test_realized_projection_and_ten_minute_full_rank(self):
        cell = self.config["cells"][-2]
        result = execute(self.config, cell, "unit_fixture", 0)["payload"]
        self.assertTrue(result["success"])
        self.assertEqual(result["design_rank"], 10)
        self.assertTrue(
            np.allclose(result["truth"], result["analytic_truth"], atol=1e-10)
        )
        self.assertEqual(result["observed_rows"], 2060)

    def test_missing_observations_not_filled(self):
        cell = self.config["cells"][1]
        a = generate(self.config, cell, "unit_fixture", 2)
        self.assertLess(len(a["times"]), cell["subjects"] * 20)
        self.assertEqual(len(a["times"]), len(a["values"]))
        self.assertEqual(len(set(zip(a["ids"], a["times"]))), len(a["times"]))

    def test_fitting_failure_remains_in_denominator(self):
        cfg = copy.deepcopy(self.config)
        cfg["minimum_support"] = 41
        r = execute(cfg, self.cell, "unit_fixture", 0)["payload"]
        self.assertFalse(r["success"])
        self.assertFalse(r["projection_covered"])
        self.assertIn("support", r["failure_reason"])

    def test_exclusive_checkpoint_duplicate_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            item = {
                "payload": {"x": 3},
                "payload_sha256": digest({"x": 3}),
                "execution": {"host": "a"},
            }
            first_hash = DRIVER.publish(path, item)
            duplicate = copy.deepcopy(item)
            duplicate["execution"]["host"] = "b"
            self.assertEqual(DRIVER.publish(path, duplicate), first_hash)
            conflict = {"payload": {"x": 4}, "payload_sha256": digest({"x": 4})}
            with self.assertRaises(ValueError):
                DRIVER.publish(path, conflict)
            self.assertEqual(DRIVER.sha(path), first_hash)
            altered = json.loads(path.read_text())
            altered["payload"]["x"] = 99
            path.write_text(json.dumps(altered))
            with self.assertRaises(ValueError):
                DRIVER.publish(path, item)

    def test_journal_recovery_detects_hash_change(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "results").mkdir()
            path = out / "results" / "task.json"
            item = {"payload": {"x": 3}, "payload_sha256": digest({"x": 3})}
            h = DRIVER.publish(path, item)
            journal = out / "checkpoint_journal.jsonl"
            journal.write_bytes(
                DRIVER.canonical({"task": "task", "file_sha256": h}) + b"\n"
            )
            self.assertEqual(DRIVER.recover(out)["task"], item)
            path.write_text("{}")
            with self.assertRaises(ValueError):
                DRIVER.recover(out)

    def test_equivalence_rejects_discrete_mismatch(self):
        DRIVER.compare_payloads(
            {"input_sha256": "abc", "x": [1.0]},
            {"input_sha256": "abc", "x": [1.0 + 1e-12]},
            1e-9,
            1e-10,
        )
        with self.assertRaises(ValueError):
            DRIVER.compare_payloads(
                {"input_sha256": "abc"}, {"input_sha256": "def"}, 1e-9, 1e-10
            )


if __name__ == "__main__":
    unittest.main()
