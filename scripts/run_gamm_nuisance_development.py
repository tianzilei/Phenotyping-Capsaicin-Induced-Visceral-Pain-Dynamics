"""Run a fixed, wholly synthetic nuisance-parameter diagnostic on remote R."""

import argparse
import importlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from distributed import Client

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from capsaicin.distributed_r import canonical, sha_bytes
from capsaicin.distributed_r_plan import r_seed
from diagnose_dask_R_precision import portable
from run_dask_R_analysis import install, preflight, python_environment
from run_dask_derivative_development import publish, write_new, sha


def synthetic_request(config, end, variance, rho, replicate, correlated):
    label = f"T{end}_v{variance}_rho{rho}"
    master = config["master_seed"]
    raw = bytes.fromhex(sha_bytes(f"{master}|{label}|{replicate}|generation".encode()))
    rng = np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(raw, dtype="<u4").tolist())
    )
    grid = np.arange(1, end + 1)
    n = config["people"]
    mean = 3 + 0.05 * grid + 0.5 * np.sin(np.pi * grid / 20)
    covariance = config["residual_variance"] * np.power(
        rho, np.abs(grid[:, None] - grid[None, :])
    )
    offset = rng.normal(0, np.sqrt(variance), (n, 1))
    noise = rng.normal(size=(n, end)) @ np.linalg.cholesky(covariance).T
    y = mean + offset + noise
    d = dict(person=[], time=[], vas=[])
    for person in range(n):
        keep = (
            (~np.isin(grid, [5, 10])) if person % 5 == 0 else np.ones(end, dtype=bool)
        )
        for t, v in zip(grid[keep], y[person, keep]):
            d["person"].append(f"synthetic_{person:04d}")
            d["time"].append(int(t))
            d["vas"].append(float(v))
    return dict(
        task=f"{label}_r{replicate:03d}_CAR1{int(correlated)}",
        seed=r_seed(master, label, replicate),
        k=6,
        correlated=correlated,
        grid=grid.tolist(),
        data=d,
    ), mean


def run(config_path, pilot, qa_path, output, scheduler):
    if output.resolve().is_relative_to(ROOT):
        raise ValueError("Use a new Git-external output directory")
    config = json.loads(config_path.read_bytes())
    frozen = json.loads((pilot / "run_manifest.json").read_bytes())
    qa = json.loads(qa_path.read_bytes())
    if len(qa) != 2 or any(q["result"]["status"] != "estimated" for q in qa):
        raise ValueError("Diagnostic serializer QA unavailable")
    output.mkdir(parents=True, exist_ok=False)
    (output / "results").mkdir()
    (output / "snapshot").mkdir()
    names = [
        "scripts/run_gamm_nuisance_development.py",
        "R/gamm_diagnostics_backend.R",
        "R/vas_models.R",
        "dependencies/r-runtime-20261003-v1.csv",
        "src/capsaicin/distributed_r.py",
        "src/capsaicin/distributed_r_plan.py",
        "scripts/diagnose_dask_R_precision.py",
        "scripts/run_dask_R_analysis.py",
        str(config_path.relative_to(ROOT)),
    ]
    hashes = {}
    for name in names:
        p = output / "snapshot" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((ROOT / name).read_bytes())
        hashes[name] = sha(p)
    assets = {
        n: (pilot / "snapshot" / n).read_bytes() for n in frozen["R_assets_sha256"]
    }
    for name in ["R/vas_models.R", "dependencies/r-runtime-20261003-v1.csv"]:
        if sha(ROOT / name) != frozen["snapshot_sha256"][name]:
            raise ValueError("Original estimator/runtime changed")
    assets["R/distributed_vas_backend.R"] = (
        output / "snapshot/R/gamm_diagnostics_backend.R"
    ).read_bytes()
    ah = {n: sha_bytes(b) for n, b in assets.items()}
    if ah != qa[0]["assets_sha256"]:
        raise ValueError("Diagnostic assets differ from synthetic QA")
    specs = list(
        itertools.product(
            config["intervals"],
            config["random_intercept_variance"],
            config["rho"],
            range(config["replicates_per_DGP_cell"]),
            [True, False],
        )
    )
    write_new(
        output / "manifest.json",
        dict(
            created_utc=datetime.now(timezone.utc).isoformat(),
            config=config,
            config_sha256=sha_bytes(canonical(config)),
            sources_sha256=hashes,
            R_assets_sha256=ah,
            diagnostic_QA_sha256=sha(qa_path),
            jobs=len(specs),
            runtime=frozen["config"]["runtime"],
            python=sys.version,
            git_revision=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            real_participant_data_used=False,
            primary_p_q=None,
        ),
    )
    bundle = next(pilot.glob("capsaicin_R_*.zip"))
    sys.path.insert(0, str(bundle))
    module = importlib.import_module(bundle.stem + ".distributed_r")
    rows = []
    index = 0
    pending = {}
    last = 0
    with Client(scheduler, set_as_default=False) as client:
        ready = preflight(client, frozen["config"])
        workers = ready["selected_workers"]
        if not workers or any(client.processing(workers=workers).values()):
            raise RuntimeError("No idle R workers")
        env = client.run(
            portable(python_environment),
            (pilot / "snapshot" / frozen["config"]["python_lock"]).read_text(),
            workers=workers,
        )
        if any(env.values()):
            raise ValueError("Python lock mismatch")
        name = bundle.stem + "_" + sha(bundle)[:16] + ".zip"
        client.run_on_scheduler(
            portable(install), bundle.read_bytes(), sha(bundle), name
        )
        client.run(
            portable(install), bundle.read_bytes(), sha(bundle), name, workers=workers
        )
        write_new(
            output / "workers.json", dict(readiness=ready, Python_lock_issues=env)
        )
        while index < len(specs) or pending:
            while index < len(specs) and len(pending) < len(workers):
                spec = specs[index]
                index += 1
                request, truth = synthetic_request(config, *spec)
                f = client.submit(
                    module.execute_r,
                    frozen["config"]["runtime"],
                    assets,
                    ah,
                    request,
                    workers=workers,
                    allow_other_workers=False,
                    pure=False,
                    retries=0,
                )
                pending[f] = (spec, request, truth)
            for f in [f for f in pending if f.done()]:
                spec, request, truth = pending.pop(f)
                result = f.result()
                f.release()
                payload = dict(
                    spec=list(spec),
                    request_sha256=result["request_sha256"],
                    config_sha256=sha_bytes(canonical(config)),
                    result=result,
                )
                file_hash = publish(
                    output / "results" / (request["task"] + ".json"),
                    dict(payload=payload, payload_sha256=sha_bytes(canonical(payload))),
                )
                with (output / "journal.jsonl").open("ab") as h:
                    h.write(
                        canonical(dict(task=request["task"], file_sha256=file_hash))
                        + b"\n"
                    )
                    h.flush()
                r = result["result"]
                end, variance, rho, replicate, correlated = spec
                row = dict(
                    task=request["task"],
                    end=end,
                    true_intercept_variance=variance,
                    true_residual_variance=config["residual_variance"],
                    true_rho=rho,
                    replicate=replicate,
                    fitted_CAR1=correlated,
                    status=r["status"],
                    reason=r.get("reason"),
                    request_sha256=result["request_sha256"],
                    peak_R_RSS=result["peak_sampled_R_RSS"],
                    seconds=result["seconds"],
                )
                if r["status"] == "estimated":
                    vc = dict(zip(r["VarCorr_rows"], r["VarCorr_values"]))
                    iv = float(vc["(Intercept)"][0])
                    rv = float(vc["Residual"][0])
                    row.update(
                        curve_RMSE=float(
                            np.sqrt(np.mean((np.asarray(r["curve"]) - truth) ** 2))
                        ),
                        fitted_intercept_variance=iv,
                        fitted_residual_variance=rv,
                        fitted_rho=r["rho"],
                        intercept_numerically_small=iv
                        < config["random_intercept_numerically_small_threshold"],
                        apVar_finite_matrix=r["apVar_finite_matrix"],
                        apVar_positive_definite=r["apVar_positive_definite"],
                        apVar_message=r["apVar_message"],
                        warnings="; ".join(r["warnings"]),
                    )
                rows.append(row)
            if time.monotonic() - last > 15:
                print(
                    json.dumps(
                        dict(
                            completed=len(rows), total=len(specs), pending=len(pending)
                        )
                    ),
                    flush=True,
                )
                last = time.monotonic()
            time.sleep(0.05)
    if len(rows) != len(specs) or len({r["task"] for r in rows}) != len(specs):
        raise ValueError("Synthetic roster mismatch")
    pd.DataFrame(sorted(rows, key=lambda r: r["task"])).to_csv(
        output / "synthetic_diagnostics.csv", index=False
    )
    write_new(
        output / "completion.json",
        dict(
            status="completed_synthetic_development_not_confirmation",
            jobs=len(rows),
            estimated=sum(r["status"] == "estimated" for r in rows),
            failures=sum(r["status"] != "estimated" for r in rows),
            primary_p_q=None,
            real_participant_data_used=False,
            outputs_sha256={p.name: sha(p) for p in output.iterdir() if p.is_file()},
        ),
    )
    print(
        json.dumps(
            dict(
                output=str(output),
                jobs=len(rows),
                status="completed_synthetic_development_not_confirmation",
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/gamm_nuisance_development_20261004_v1.json",
    )
    p.add_argument("--pilot", type=Path, required=True)
    p.add_argument("--QA", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--scheduler", default="tcp://192.0.2.54:8786")
    a = p.parse_args()
    run(
        a.config.resolve(),
        a.pilot.resolve(),
        a.QA.resolve(),
        a.output.resolve(),
        a.scheduler,
    )
