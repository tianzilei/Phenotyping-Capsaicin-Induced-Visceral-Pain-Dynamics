import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from capsaicin.distributed_r import execute_r, canonical, run_process
from capsaicin.distributed_r_plan import subject_indices, request_for, long_rows
import numpy as np


class DistributedRTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        exe = root / "Rscript"
        exe.write_text("synthetic executable placeholder")
        lib = root / "library"
        lib.mkdir()
        self.runtime = dict(rscript=str(exe), library=str(lib))
        self.assets = {"R/distributed_vas_backend.R": b"# synthetic fixture"}
        self.hashes = {k: hashlib.sha256(v).hexdigest() for k, v in self.assets.items()}
        self.request = dict(task="synthetic", kind="qa", seed=7)

    def test_rejects_corrupt_asset_before_subprocess(self):
        with patch("capsaicin.distributed_r.run_process") as run:
            with self.assertRaises(ValueError):
                execute_r(
                    self.runtime,
                    self.assets,
                    {k: "wrong" for k in self.assets},
                    self.request,
                )
            run.assert_not_called()

    def test_rejects_parent_asset_path(self):
        assets = {"../escape.R": b"# synthetic"}
        with self.assertRaises(ValueError):
            execute_r(
                self.runtime,
                assets,
                {k: hashlib.sha256(v).hexdigest() for k, v in assets.items()},
                self.request,
            )

    def test_no_invented_result_after_failed_process(self):
        with patch(
            "capsaicin.distributed_r.run_process",
            return_value=subprocess.CompletedProcess([], 1, "", "synthetic failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                execute_r(self.runtime, self.assets, self.hashes, self.request)

    def test_result_identity_and_explicit_runtime(self):
        def fake_run(command, **kwargs):
            root = Path(kwargs["cwd"])
            self.assertEqual(command[0], self.runtime["rscript"])
            self.assertEqual(command[-1], self.runtime["library"])
            self.assertEqual(kwargs["env"]["OMP_NUM_THREADS"], "1")
            self.assertEqual(kwargs["env"]["R_LIBS_USER"], self.runtime["library"])
            self.assertEqual(
                (root / "request.json").read_bytes(), canonical(self.request)
            )
            (root / "result.json").write_text(
                json.dumps(dict(task="wrong_task", status="PASS"))
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("capsaicin.distributed_r.run_process", side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, "task mismatch"):
                execute_r(self.runtime, self.assets, self.hashes, self.request)

    def test_nonfinite_request_is_not_silently_replaced(self):
        with self.assertRaises(ValueError):
            canonical(dict(value=float("nan")))

    def test_R_child_memory_limit_is_enforced(self):
        with self.assertRaises(MemoryError):
            run_process(
                [sys.executable, "-c", "import time; time.sleep(3)"],
                cwd=self.tmp.name,
                env=None,
                timeout=5,
                rss_limit=1,
            )

    def test_logical_subject_stream_ignores_batch_and_model(self):
        rows = [subject_indices(7, "complete10", rep, 20) for rep in range(10)]
        split = [subject_indices(7, "complete10", rep, 20) for rep in range(5)]
        split += [subject_indices(7, "complete10", rep, 20) for rep in range(5, 10)]
        self.assertEqual(rows, split)
        self.assertNotEqual(rows[0], subject_indices(7, "complete20", 0, 20))

    def test_whole_person_fold_isolation_and_exact_time_payload(self):
        config = dict(master_seed=7, complete=dict(reconstruction=dict(folds=5)))
        data = dict(complete10=dict(n_people=20, y=[[2] * 10 for _ in range(20)]))
        seen = []
        for fold in range(5):
            job = dict(
                id=str(fold),
                stage="reconstruction",
                repeat=0,
                fold=fold,
                cell=dict(id="F10", module="complete", end=10, frame="complete10"),
            )
            request = request_for(config, data, job)
            self.assertFalse(set(request["train"]) & set(request["test"]))
            seen += request["test"]
        self.assertEqual(sorted(seen), list(range(20)))
        long = dict(person=["p0000", "p0000"], time=[1, 3], vas=[0, 2])
        job = dict(
            id="reference",
            stage="reference",
            cell=dict(
                id="G10",
                module="gamm",
                end=10,
                frame="observed10",
                k=6,
                correlated=True,
            ),
        )
        request = request_for(config, dict(observed10=dict(long=long, n_people=1)), job)
        self.assertEqual(request["data"], long)

    def test_complete_cohort_also_has_exact_GAMM_long_rows(self):
        values = np.array([[0, 1, 2], [3, np.nan, 4]], float)
        complete = np.flatnonzero(np.isfinite(values).all(axis=1))
        frame = dict(
            n_people=1, y=values[complete].tolist(), long=long_rows(values, complete, 3)
        )
        request = request_for(
            dict(master_seed=7),
            dict(complete3=frame),
            dict(
                id="reference",
                stage="reference",
                cell=dict(
                    id="G3_complete",
                    module="gamm",
                    end=3,
                    frame="complete3",
                    k=3,
                    correlated=True,
                ),
            ),
        )
        self.assertEqual(
            request["data"],
            dict(person=["p0000"] * 3, time=[1, 2, 3], vas=[0.0, 1.0, 2.0]),
        )
        observed = long_rows(values, [1], 3)
        self.assertEqual(observed["time"], [1, 3])
