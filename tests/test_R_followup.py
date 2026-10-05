"""Synthetic checks for bundle identity and independent FPCA verification."""

import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
from run_dask_R_analysis import install
from verify_complete_FPCA_replicates import independent_FPCA
from run_gamm_nuisance_development import synthetic_request


class FollowupTests(unittest.TestCase):
    def test_archive_conflict_preserves_existing_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            scheduler = SimpleNamespace(local_directory=temp)
            old = b"old archive metadata"
            new = b"new archive metadata"
            install(
                old,
                hashlib.sha256(old).hexdigest(),
                "bundle.zip",
                dask_scheduler=scheduler,
            )
            with self.assertRaises(ValueError):
                install(
                    new,
                    hashlib.sha256(new).hexdigest(),
                    "bundle.zip",
                    dask_scheduler=scheduler,
                )
            addressed = "bundle_" + hashlib.sha256(new).hexdigest()[:16] + ".zip"
            path = install(
                new,
                hashlib.sha256(new).hexdigest(),
                addressed,
                dask_scheduler=scheduler,
            )
            self.assertEqual(Path(path).read_bytes(), new)
            self.assertEqual((Path(temp) / "bundle.zip").read_bytes(), old)

    def test_analytic_weighted_spectrum_and_portability(self):
        from types import FunctionType
        from distributed.protocol.pickle import dumps, loads

        y = np.vstack([np.diag([4.0, 3.0, 2.0, 1.0]), -np.diag([4.0, 3.0, 2.0, 1.0])])
        request = dict(data=dict(y=y.tolist()), grid=[1, 2, 3, 4], draw=list(range(8)))
        # Trapezoid-weighted sums of squares: 18,16,8,1, ordered descending.
        saved = dict(
            cumulative_fve=np.cumsum([18.0, 16.0, 8.0, 1.0]) / 43,
            angle_deg=[0.0] * 4,
            matched_inner=[1.0] * 4,
        )
        checker = FunctionType(
            independent_FPCA.__code__,
            {"__builtins__": __builtins__, "__name__": "__main__"},
            "check",
            independent_FPCA.__defaults__,
        )
        # At exactly zero angle, acos amplifies O(eps) SVD roundoff to O(sqrt(eps)).
        # This analytic-fixture allowance does not change the frozen real audit.
        self.assertEqual(
            loads(dumps(checker))([(request, saved)], atol=2e-6)["status"], "PASS"
        )
        saved["cumulative_fve"][0] += 0.1
        with self.assertRaises(ValueError):
            independent_FPCA([(request, saved)])

    def test_zero_variance_and_invalid_draw_rejected(self):
        request = dict(
            data=dict(y=np.ones((8, 4)).tolist()),
            grid=[1, 2, 3, 4],
            draw=list(range(8)),
        )
        with self.assertRaises(ValueError):
            independent_FPCA([(request, {})])
        request["data"]["y"] = np.arange(32.0).reshape(8, 4).tolist()
        request["draw"][0] = 8
        with self.assertRaises(ValueError):
            independent_FPCA([(request, {})])

    def test_synthetic_paired_models_preserve_actual_gaps(self):
        config = dict(master_seed=84620, people=10, residual_variance=0.25)
        a, truth = synthetic_request(config, 20, 0.25, 0.85, 0, True)
        b, _ = synthetic_request(config, 20, 0.25, 0.85, 0, False)
        self.assertEqual(a["data"], b["data"])
        self.assertNotEqual(a["task"], b["task"])
        self.assertEqual(a["seed"], b["seed"])
        times = [
            t
            for p, t in zip(a["data"]["person"], a["data"]["time"])
            if p == "synthetic_0000"
        ]
        self.assertNotIn(5, times)
        self.assertNotIn(10, times)
        self.assertIn(6, times)
        self.assertIn(11, times)
        self.assertEqual(len(a["data"]["vas"]), 196)
        self.assertTrue(
            np.allclose(
                truth,
                3
                + 0.05 * np.arange(1, 21)
                + 0.5 * np.sin(np.pi * np.arange(1, 21) / 20),
            )
        )
        c, _ = synthetic_request(config, 20, 0.25, 0.85, 1, True)
        self.assertNotEqual(a["data"]["vas"], c["data"]["vas"])


if __name__ == "__main__":
    unittest.main()
