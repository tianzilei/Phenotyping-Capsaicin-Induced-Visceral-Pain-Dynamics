import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import numpy as np
import pandas as pd
from run_candidate_associations import prepare, coefficient


class FixedEffects(unittest.TestCase):
    def test_cluster_weights_equal_relabelled_copies(self):
        rng = np.random.default_rng(82)
        d = pd.DataFrame(
            {
                "person_id": np.repeat(np.arange(12), 4),
                "block": np.tile(np.arange(4), 12),
            }
        )
        d["vas_mean"] = rng.normal(size=len(d))
        d["value"] = (
            1.3 * d.vas_mean
            + 0.2 * d.block
            + np.repeat(rng.normal(size=12), 4)
            + rng.normal(size=len(d))
        )
        take = rng.integers(12, size=12)
        weights = np.bincount(take, minlength=12)
        prep, _ = prepare(d)
        copies = []
        for i, sid in enumerate(take):
            q = d[d.person_id == sid].copy()
            q["person_id"] = i
            copies.append(q)
        expanded, _ = prepare(pd.concat(copies))
        self.assertAlmostEqual(
            coefficient(prep, weights), coefficient(expanded), places=12
        )

    def test_rank_and_duplicate_blocks(self):
        d = pd.DataFrame(
            {
                "person_id": ["a", "a"],
                "block": [1, 1],
                "vas_mean": [1, 2],
                "value": [2, 3],
            }
        )
        with self.assertRaises(ValueError):
            prepare(d)
        self.assertIsNone(coefficient(None))


if __name__ == "__main__":
    unittest.main()
