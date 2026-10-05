"""Independent remote NumPy checks at frozen positions in the new R FPCA run."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import FunctionType
import numpy as np
from distributed import Client

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from capsaicin.distributed_r_plan import request_for
from run_dask_derivative_development import recover, sha, write_new


def independent_FPCA(items, rtol=1e-8, atol=1e-8):
    import itertools
    import numpy as np

    differences = dict(cumulative_fve=0.0, angle_deg=0.0, matched_inner=0.0)

    def fit(y, grid):
        if (
            not np.isfinite(y).all()
            or not np.isfinite(grid).all()
            or not (np.diff(grid) > 0).all()
        ):
            raise ValueError("Invalid FPCA input")
        weights = np.empty(len(grid))
        dt = np.diff(grid)
        weights[0] = dt[0] / 2
        weights[-1] = dt[-1] / 2
        weights[1:-1] = (dt[:-1] + dt[1:]) / 2
        centered = y - y.mean(axis=0)
        singular = np.linalg.svd(centered * np.sqrt(weights), full_matrices=False)
        values = singular[1] ** 2
        if values.sum() <= 1e-12:
            raise ValueError("No between-person variation")
        return (
            np.cumsum(values[:4] / values.sum()),
            singular[2][:4].T / np.sqrt(weights[:, None]),
            weights,
        )

    for request, saved in items:
        y = np.asarray(request["data"]["y"], float)
        grid = np.asarray(request["grid"], float)
        ref_fve, ref, weights = fit(y, grid)
        draw = np.asarray(request["draw"], int)
        if len(draw) != len(y) or np.any(draw < 0) or np.any(draw >= len(y)):
            raise ValueError("Invalid whole-person draw")
        fve, phi, _ = fit(y[draw], grid)
        inner = ref.T @ (weights[:, None] * phi)
        permutations = list(itertools.permutations(range(4)))
        objectives = [sum(abs(inner[j, p[j]]) for j in range(4)) for p in permutations]
        perm = permutations[int(np.argmax(objectives))]
        matched = np.asarray([abs(inner[j, perm[j]]) for j in range(4)])
        angles = []
        for k in range(1, 5):
            s = np.linalg.svd(
                ref[:, :k].T @ (weights[:, None] * phi[:, :k]), compute_uv=False
            )
            angles.append(np.degrees(np.arccos(np.clip(s, 0, 1))).max())
        for key, expected in [
            ("cumulative_fve", fve),
            ("angle_deg", angles),
            ("matched_inner", matched),
        ]:
            actual = np.asarray(saved[key], float)
            expected = np.asarray(expected)
            if actual.shape != expected.shape or not np.allclose(
                actual, expected, rtol=rtol, atol=atol
            ):
                raise ValueError("Independent FPCA numerical mismatch: " + key)
            differences[key] = max(
                differences[key], float(np.max(np.abs(actual - expected)))
            )
    return dict(status="PASS", checked=len(items), max_absolute_difference=differences)


def verify(run, output, config_path, scheduler):
    if output.resolve().is_relative_to(ROOT):
        raise ValueError("Audit stays outside Git")
    config = json.loads(config_path.read_bytes())
    frozen = json.loads((run / "run_manifest.json").read_bytes())
    data = json.loads((run / "private_inputs/data.json").read_bytes())
    records = recover(run)
    if sha(run / "private_inputs/data.json") != frozen["private_data_sha256"]:
        raise ValueError("Input hash changed")
    selected = []
    items = []
    for end in config["intervals"]:
        for index in config["replicate_indices_zero_based"]:
            job = next(
                j
                for j in frozen["jobs"]
                if j["stage"] == "complete"
                and j["cell"]["end"] == end
                and j["start"] <= index < j["stop"]
            )
            p = records[job["id"]]["payload"]
            request = request_for(frozen["config"], data, job)
            r = p["result"]["replicates"][index - job["start"]]
            if r["status"] != "estimated":
                raise ValueError(
                    "Selected replicate failed; retain failure, do not choose replacement"
                )
            items.append(
                (
                    dict(
                        data=request["data"],
                        grid=request["grid"],
                        draw=request["draws"][index - job["start"]],
                    ),
                    r,
                )
            )
            selected.append(
                dict(
                    cell=job["cell"]["id"],
                    replicate=index,
                    checkpoint=job["id"],
                    payload_sha256=records[job["id"]]["payload_sha256"],
                )
            )
    checker = FunctionType(
        independent_FPCA.__code__,
        {"__builtins__": __builtins__, "__name__": "__main__"},
        "independent_FPCA",
        independent_FPCA.__defaults__,
    )
    with Client(scheduler, set_as_default=False) as client:
        workers = [
            a
            for a, w in client.scheduler_info()["workers"].items()
            if a.startswith("tcp://192.0.2.186:") and w["nthreads"] == 1
        ]
        idle = [a for a in workers if not client.processing(workers=workers)[a]][:8]
        if not idle:
            raise RuntimeError("No idle Windows verifier workers")
        futures = [
            client.submit(
                checker,
                items[i :: len(idle)],
                config["relative_tolerance"],
                config["absolute_tolerance"],
                workers=[w],
                allow_other_workers=False,
                pure=False,
                retries=0,
            )
            for i, w in enumerate(idle)
        ]
        results = client.gather(futures)
        for f in futures:
            f.release()
    write_new(
        output,
        dict(
            status="INDEPENDENT_SELECTED_FPCA_NUMERICS_VERIFIED",
            created_utc=datetime.now(timezone.utc).isoformat(),
            run_directory=str(run),
            configuration=config,
            config_sha256=sha(config_path),
            verifier_sha256=sha(Path(__file__)),
            run_manifest_sha256=sha(run / "run_manifest.json"),
            selected=selected,
            workers=idle,
            results=results,
            scope="fixed 20 replicate numeric checks; not all 200000 replicate numerics or population coverage",
        ),
    )
    print(
        json.dumps(
            dict(
                output=str(output),
                checked=sum(r["checked"] for r in results),
                status="PASS",
            )
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/dask_R_followup_verification_20261004_v1.json",
    )
    p.add_argument("--scheduler", default="tcp://192.0.2.54:8786")
    a = p.parse_args()
    verify(a.run.resolve(), a.output.resolve(), a.config.resolve(), a.scheduler)
