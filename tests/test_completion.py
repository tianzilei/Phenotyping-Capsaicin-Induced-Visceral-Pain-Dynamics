"""Synthetic-only tests of time, fold and subject-bootstrap contracts."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
import pandas as pd
from capsaicin.completion import (
    candidate_panel,
    fe_sufficient,
    solve_fe,
    post_stop_grid,
    select_shapelets,
    shapelet_distances,
    relative_manifest_path,
)


class CompletionContracts(unittest.TestCase):
    def test_manifest_windows_relative_paths_and_traversal(self):
        self.assertEqual(
            relative_manifest_path(
                Path("/synthetic/run"), "code_snapshot\\src\\file.py"
            ),
            Path("/synthetic/run/code_snapshot/src/file.py"),
        )
        for bad in [
            "../file.py",
            "folder\\..\\file.py",
            "C:\\outside.py",
            "/outside.py",
        ]:
            with self.assertRaises(ValueError):
                relative_manifest_path(Path("/synthetic/run"), bad)

    def test_weighted_person_bootstrap_matches_expanded_fixed_effects(self):
        rng = np.random.default_rng(31)
        data = pd.DataFrame(
            dict(person_id=np.repeat(np.arange(8), 4), block=np.tile(np.arange(4), 8))
        )
        data["x"] = rng.normal(size=len(data))
        data["z"] = rng.normal(size=len(data))
        data["y"] = (
            1.4 * data.x
            - 0.8 * data.z
            + 0.7 * data.block
            + np.repeat(rng.normal(size=8), 4)
        )
        prep = fe_sufficient(data, "y", ["x", "z"])
        take = np.array([0, 0, 1, 2, 4, 5, 5, 7])
        weighted = solve_fe(prep, np.bincount(take, minlength=8))
        copies = []
        for i, person in enumerate(take):
            part = data[data.person_id == person].copy()
            part["person_id"] = i
            copies.append(part)
        expanded = pd.concat(copies, ignore_index=True)
        explicit = np.column_stack(
            [
                expanded[["x", "z"]],
                pd.get_dummies(expanded.person_id, dtype=float),
                pd.get_dummies(expanded.block, drop_first=True, dtype=float),
            ]
        )
        expected = np.linalg.lstsq(explicit, expanded.y, rcond=None)[0]
        np.testing.assert_allclose(weighted["coefficients"], expected[:2], atol=1e-11)
        np.testing.assert_allclose(
            solve_fe(fe_sufficient(expanded, "y", ["x", "z"]))["coefficients"],
            expected[:2],
            atol=1e-11,
        )

    def test_rank_duplicate_and_constant_candidates(self):
        data = pd.DataFrame(
            dict(
                person_id=["a", "a", "b", "b"],
                block=[0, 1, 0, 1],
                x=[1, 1, 2, 2],
                y=[1, 2, 3, 4],
            )
        )
        self.assertIsNone(solve_fe(fe_sufficient(data, "y", ["x"])))
        self.assertTrue(candidate_panel(data, ["x", "y"], ["x"]).empty)
        data.loc[1, "block"] = 0
        with self.assertRaises(ValueError):
            candidate_panel(data, ["x", "y"])

    def test_algebraic_scenarios_preserve_observed_zero_and_unknown_missing(self):
        frame = pd.DataFrame(
            [
                {
                    **{f"VAS_{i}min": "E" for i in range(1, 21)},
                    "VAS_1min": "0",
                    "VAS_2min": "2",
                },
                {
                    **{f"VAS_{i}min": "T" for i in range(1, 21)},
                    "VAS_1min": "4",
                    "VAS_2min": "",
                },
            ]
        )
        before = frame.copy(deep=True)
        curves, areas, summary = post_stop_grid(frame, [0, 10], [0, 10])
        pd.testing.assert_frame_equal(frame, before)
        first = [r for r in curves if r["time_min"] == 1]
        self.assertTrue(all(r["hypothetical_mean_low"] == 2 for r in first))
        second = next(r for r in curves if r["time_min"] == 2)
        self.assertEqual(second["n_other_missing"], 1)
        self.assertEqual(
            second["hypothetical_mean_high"] - second["hypothetical_mean_low"], 5
        )
        self.assertAlmostEqual(
            min(r["hypothetical_auc_low"] for r in areas),
            summary["algebraic_auc_lower"],
        )
        self.assertAlmostEqual(
            max(r["hypothetical_auc_high"] for r in areas),
            summary["algebraic_auc_upper"],
        )

    def test_shapelets_are_from_training_prefix_only(self):
        train = np.array(
            [
                [0.0, 0, 1, 1, 0, 0],
                [0.0, 1, 1, 1, 0, 0],
                [8.0, 9, 9, 8, 9, 8],
                [9.0, 9, 8, 9, 8, 9],
            ]
        )
        shapes, origins = select_shapelets(train, [0, 0, 1, 1], 5, 10, 29)
        for shape, origin in zip(shapes, origins):
            np.testing.assert_equal(
                shape,
                train[
                    origin["training_row"],
                    origin["start_index"] : origin["start_index"] + 5,
                ],
            )
        self.assertEqual(shapelet_distances(train, shapes).shape, (4, 2))
        with self.assertRaises(ValueError):
            shapelet_distances([[1, 2, np.nan, 3, 4]], shapes)


if __name__ == "__main__":
    unittest.main()
