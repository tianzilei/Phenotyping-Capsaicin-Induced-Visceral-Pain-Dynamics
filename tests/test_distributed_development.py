"""Logical stream separation and reproducibility on synthetic observations."""

import json
from pathlib import Path
import unittest
import numpy as np
from capsaicin.distributed_development import generate
from capsaicin.random_streams import generator


class DevelopmentTests(unittest.TestCase):
    def test_repeated_calls_and_stages(self):
        root = Path(__file__).resolve().parents[1]
        config = json.loads(
            (root / "config/dask_derivative_development_20261003_v1.json").read_text()
        )
        cell = config["cells"][0]
        a = generate(config, cell, "smoke", 0)
        generate(config, cell, "smoke", 4)
        b = generate(config, cell, "smoke", 0)
        c = generate(config, cell, "development", 0)
        np.testing.assert_array_equal(a["values"], b["values"])
        self.assertFalse(np.array_equal(a["values"], c["values"]))

    def test_unambiguous_keys(self):
        self.assertFalse(
            np.array_equal(
                generator(1, "23").integers(100, size=100),
                generator(12, "3").integers(100, size=100),
            )
        )
        whole = [
            generator(7, "draw", i).integers(30, size=30).tolist() for i in range(8)
        ]
        split = [
            generator(7, "draw", i).integers(30, size=30).tolist() for i in range(4)
        ] + [
            generator(7, "draw", i).integers(30, size=30).tolist() for i in range(4, 8)
        ]
        self.assertEqual(whole, split)
