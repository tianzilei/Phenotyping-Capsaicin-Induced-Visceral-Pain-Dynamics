"""Protect complete current numbering, estimators and output isolation."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.aligned_artifacts import export_tables


class AlignedReleaseTests(unittest.TestCase):
    def test_complete_numbering_and_byte_preservation(self):
        config = json.loads(
            (ROOT / "config/aligned_artifacts_20261027_v1.json").read_text()
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "tables"
            export_tables(ROOT, config, destination)
            self.assertEqual(len(list(destination.glob("*.csv"))), 31)
            for name, source in config["table_sources"].items():
                self.assertEqual(
                    (destination / name).read_bytes(), (ROOT / source).read_bytes()
                )
        altered = {**config, "table_sources": dict(config["table_sources"])}
        altered["table_sources"].pop("TableS28_common_support_timing_all432.csv")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "exactly"):
                export_tables(ROOT, altered, Path(directory) / "tables")

    def test_synthetic_cluster_covariance_and_multiplicity(self):
        folder = ROOT / "scripts/physiology_20261017"
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "CAPSAICIN_ANALYSIS_ROOT": directory,
                    "CAPSAICIN_PHYSIOLOGY_RUN": str(Path(directory) / "new"),
                },
            ):
                sys.path.insert(0, str(folder))
                try:
                    spec = importlib.util.spec_from_file_location(
                        "synthetic_inference", folder / "analyse.py"
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                finally:
                    sys.path.remove(str(folder))
                self.assertFalse(module.OUT.exists())
                rng = np.random.default_rng(17)
                groups = np.repeat(np.arange(12), 4)
                blocks = np.tile(np.arange(1, 5), 12)
                x = rng.normal(size=48)
                y = (
                    0.7 * x
                    + np.repeat(rng.normal(size=12), 4)
                    + blocks * 0.2
                    + rng.normal(size=48)
                )
                data = pd.DataFrame(
                    {"person_id": groups, "block": blocks, "x": x, "y": y}
                )
                prepared = module.prepare(data, "y", ["x"])
                result = module.fit(prepared)
                design = np.column_stack(
                    [x, pd.get_dummies(blocks, drop_first=True), pd.get_dummies(groups)]
                ).astype(float)
                bread = np.linalg.inv(np.einsum("ni,nj->ij", design, design))
                beta = np.einsum("ij,nj,n->i", bread, design, y)
                residual = y - np.einsum("ni,i->n", design, beta)
                scores = np.array(
                    [
                        np.einsum("ni,n->i", design[groups == g], residual[groups == g])
                        for g in range(12)
                    ]
                )
                projected = np.einsum("gi,ij->gj", scores, bread)
                covariance = (
                    (12 / 11)
                    * (47 / (48 - design.shape[1]))
                    * np.einsum("gi,gj->ij", projected, projected)
                )
                self.assertAlmostEqual(result["b"][0], beta[0], places=11)
                self.assertAlmostEqual(
                    result["se"][0], np.sqrt(covariance[0, 0]), places=11
                )
                for method in ["BY", "BH"]:
                    values = np.array([0.001, 0.04, 0.2, 0.9])
                    np.testing.assert_allclose(
                        module.adjust(values, method),
                        stats.false_discovery_control(values, method=method.lower()),
                    )
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    module.prepare(pd.concat([data, data.iloc[[0]]]), "y", ["x"])
                data["x"] = 1.0
                with self.assertRaisesRegex(ValueError, "rank deficient"):
                    module.prepare(data, "y", ["x"])

    def test_fresh_run_is_required(self):
        folder = ROOT / "scripts/physiology_20261017"
        spec = importlib.util.spec_from_file_location(
            "isolated_runtime", folder / "runtime.py"
        )
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text("{}")
            output = Path(directory) / "run"
            runtime.start_run(output, config)
            with self.assertRaises(FileExistsError):
                runtime.start_run(output, config)
            with self.assertRaises(FileExistsError):
                runtime.require_missing(output, ["frozen_config.json"])


if __name__ == "__main__":
    unittest.main()
