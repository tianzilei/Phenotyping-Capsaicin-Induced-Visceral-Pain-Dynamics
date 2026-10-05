"""Freeze private R inputs and the complete job roster without starting inference."""

import argparse
import hashlib
import json
import importlib.metadata
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.distributed_observation import tokens_to_arrays
from capsaicin.distributed_r import canonical, sha_bytes
from capsaicin.distributed_r_plan import jobs, request_for, long_rows


def prepare(config_path):
    config = json.loads(config_path.read_bytes())
    source = ROOT / config["source"]["path"]
    source_manifest = ROOT / config["source"]["manifest"]
    manifest = json.loads(source_manifest.read_bytes())
    source_hash = sha_bytes(source.read_bytes())
    if source_hash != manifest["outputs_sha256"][source.name]:
        raise ValueError("Source hash mismatch")
    people = (
        pd.read_csv(source, dtype=str, keep_default_na=False)
        .sort_values("ID")
        .reset_index(drop=True)
    )
    if len(people) != config["expected_people"] or people.ID.duplicated().any():
        raise ValueError("True-person frame changed")
    values, _ = tokens_to_arrays(
        people[[f"VAS_{m}min" for m in range(1, 21)]].to_numpy()
    )
    data = {}
    supports = {}
    for end in [10, 20]:
        complete = np.flatnonzero(np.isfinite(values[:, :end]).all(axis=1))
        observed = np.flatnonzero(np.isfinite(values[:, :end]).any(axis=1))
        if len(complete) != config["expected_complete"][str(end)]:
            raise ValueError("Complete frame changed")
        data["complete" + str(end)] = dict(
            n_people=len(complete),
            y=values[complete, :end].tolist(),
            long=long_rows(values, complete, end),
        )
        long = dict(person=[], time=[], vas=[])
        Ly = []
        Lt = []
        for row in observed:
            times = np.flatnonzero(np.isfinite(values[row, :end]))
            for minute in times:
                long["person"].append(f"p{row:04d}")
                long["time"].append(int(minute + 1))
                long["vas"].append(float(values[row, minute]))
            Ly.append(values[row, times].tolist())
            Lt.append((times + 1).tolist())
        data["observed" + str(end)] = dict(
            n_people=len(observed), long=long, Ly=Ly, Lt=Lt
        )
        supports[str(end)] = dict(
            complete_people=len(complete),
            observed_people=len(observed),
            observations=len(long["vas"]),
        )
    base = Path.home() / ".local/share/capsaicin-dask/runs"
    out = base / (
        "dask_R_prepared_"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "_"
        + uuid.uuid4().hex[:8]
    )
    (out / "private_inputs").mkdir(parents=True)
    (out / "snapshot").mkdir()
    (out / "results").mkdir()
    with (out / "private_inputs/people_private.csv").open("xb") as h:
        h.write(source.read_bytes())
    with (out / "private_inputs/data.json").open("xb") as h:
        h.write(canonical(data) + b"\n")
    asset_names = [
        "R/distributed_vas_backend.R",
        "R/vas_models.R",
        "R/fpca_followup.R",
        "R/sparse_fpca.R",
        "scripts/test_vas_models.R",
        "scripts/test_sparse_fpca.R",
        "scripts/test_distributed_R_backend.R",
        "config/sparse_fpca_v1.json",
        "dependencies/r-runtime-20261003-v1.csv",
    ]
    snapshots = [
        *asset_names,
        str(config_path.relative_to(ROOT)),
        config["python_lock"],
        config["R_lock"],
        "src/capsaicin/distributed_r.py",
        "src/capsaicin/distributed_r_plan.py",
        "src/capsaicin/distributed_observation.py",
        "scripts/prepare_dask_R_analysis.py",
        "scripts/check_distributed_R_runtime.R",
        "scripts/run_dask_R_analysis.py",
    ]
    snapshots += [
        "scripts/run_dask_derivative_development.py",
        "src/capsaicin/distributed_development.py",
    ]
    hashes = {}
    for name in snapshots:
        target = out / "snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as h:
            h.write((ROOT / name).read_bytes())
        hashes[name] = sha_bytes(target.read_bytes())
    roster = jobs(config)
    # Validate every explicit request before freeze; requests themselves stay private.
    for job in roster:
        request = request_for(config, data, job)
        canonical(request)
        if "draws" in request:
            assert len(request["draws"]) == job["stop"] - job["start"]
            assert all(
                len(draw) == data[job["cell"]["frame"]]["n_people"]
                for draw in request["draws"]
            )
    frozen = dict(
        status="prepared_requires_R_and_transport_preflight_before_execution",
        created_utc=datetime.now(timezone.utc).isoformat(),
        config=config,
        config_sha256=sha_bytes(canonical(config)),
        input_sha256={
            str(source.relative_to(ROOT)): source_hash,
            str(source_manifest.relative_to(ROOT)): sha_bytes(
                source_manifest.read_bytes()
            ),
        },
        private_data_sha256=sha_bytes((out / "private_inputs/data.json").read_bytes()),
        snapshot_sha256=hashes,
        R_assets_sha256={name: hashes[name] for name in asset_names},
        supports=supports,
        jobs=roster,
        git_revision=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        dirty_diff_sha256=sha_bytes(
            subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT)
        ),
        local_driver_environment=dict(
            python=sys.version,
            platform=platform.platform(),
            packages={
                d.metadata["Name"]: d.version
                for d in importlib.metadata.distributions()
            },
        ),
        real_analysis_started=False,
        sealed_people_used=0,
        primary_p_q=None,
    )
    with (out / "run_manifest.json").open("xb") as h:
        h.write(canonical(frozen) + b"\n")
    pointer = (
        Path.home() / ".local/share/capsaicin-dask/state/latest-prepared-R-run.txt"
    )
    pointer.write_text(str(out) + "\n")
    print(
        json.dumps(
            dict(
                run_directory=str(out),
                jobs=len(roster),
                supports=supports,
                status=frozen["status"],
            )
        ),
        flush=True,
    )
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config", type=Path, default=ROOT / "config/dask_R_analysis_20261003_v1.json"
    )
    prepare(p.parse_args().config.resolve())
