"""Read-only pilot diagnostics and frozen diagnostic-only GAMM reference refits."""

import argparse
import collections
import importlib
import json
from pathlib import Path
import subprocess
import sys
from types import FunctionType
from datetime import datetime, timezone
import uuid

import numpy as np
import pandas as pd
from distributed import Client

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from capsaicin.distributed_r import canonical, sha_bytes
from capsaicin.distributed_r_plan import request_for
from run_dask_derivative_development import recover, write_new, sha
from run_dask_R_analysis import install, preflight, python_environment


def portable(function):
    """Imported CLI modules are not installed on workers; send standalone code."""
    return FunctionType(
        function.__code__,
        {"__builtins__": __builtins__, "__name__": "__main__"},
        function.__name__,
        function.__defaults__,
    )


def diagnose(pilot, output, refit=False, scheduler="tcp://192.0.2.54:8786"):
    if output.resolve().is_relative_to(ROOT):
        raise ValueError("Use a new Git-external directory")
    frozen = json.loads((pilot / "run_manifest.json").read_bytes())
    config = frozen["config"]
    completion = json.loads((pilot / "completion.json").read_bytes())
    for name, h in completion["outputs_sha256"].items():
        if sha(pilot / name) != h:
            raise ValueError("Completed pilot changed: " + name)
    for name, h in frozen["snapshot_sha256"].items():
        if sha(pilot / "snapshot" / name) != h:
            raise ValueError("Frozen pilot snapshot changed")
    records = recover(pilot)
    roster = {j["id"]: j for j in frozen["jobs"]}
    if set(records) != set(roster):
        raise ValueError("Incomplete pilot")
    for task, e in records.items():
        p = e["payload"]
        if (
            p["job"] != roster[task]
            or p["config_sha256"] != frozen["config_sha256"]
            or p["input_sha256"] != frozen["private_data_sha256"]
        ):
            raise ValueError("Pilot checkpoint identity changed")
    output.mkdir(parents=True, exist_ok=False)
    sources = [
        "scripts/diagnose_dask_R_precision.py",
        "R/gamm_diagnostics_backend.R",
        "scripts/run_dask_R_analysis.py",
    ]
    hashes = {}
    for name in sources:
        p = output / "snapshot" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((ROOT / name).read_bytes())
        hashes[name] = sha(p)
    diagnostic_config = dict(
        version="GAMM_diagnostic_only_20261004_v1",
        pilot_run=str(pilot),
        refit_reference_only=refit,
        cells=[c["id"] for c in config["gamm"]["cells"]],
        estimator="exact frozen fit_vas_gamm; same reference seed, frames, k and correlation",
        conditioning="post-fit apVar flag descriptive association only; no exclusion, causal claim or CI",
        apVar="spectrum is approximate covariance; no Hessian or unavailable optimizer exit code fabricated",
        MC_planning="B_old*(half/min(.02*range,absolute))^2, inverse-root-B heuristic only",
        no_new_bootstrap=True,
        no_parameter_tuning=True,
        primary_p_q=None,
        sealed_people_used=0,
    )
    write_new(output / "diagnostic_config.json", diagnostic_config)
    write_new(
        output / "manifest.json",
        dict(
            created_utc=datetime.now(timezone.utc).isoformat(),
            config_sha256=sha_bytes(canonical(diagnostic_config)),
            sources_sha256=hashes,
            pilot_manifest_sha256=sha(pilot / "run_manifest.json"),
            pilot_completion_sha256=sha(pilot / "completion.json"),
            pilot_input_sha256=frozen["input_sha256"],
            git_revision=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            python=sys.version,
            previous_checkpoints=len(records),
        ),
    )
    rows = []
    for stage in ["gamm", "complete", "sparse"]:
        for r in json.loads((pilot / (stage + "_summary.json")).read_bytes()):
            absolute = dict(
                curve=0.01, cumulative_fve=0.002, matched_inner=0.002, angle_deg=0.5
            )[r["metric"]]
            width = r["empirical_range_width"]
            half = r["MC_max_endpoint_half_width"]
            target = min(config["MC"]["relative_tolerance"] * width, absolute)
            ratio = half / target if target > 0 else (0 if half == 0 else None)
            rows.append(
                dict(
                    stage=stage,
                    cell=r["cell"],
                    metric=r["metric"],
                    index=r["index"],
                    old_B=r["attempted"],
                    range_width=width,
                    old_MC_half_width=half,
                    target_half_width=target,
                    ratio=ratio,
                    heuristic_B=r["attempted"] * ratio**2
                    if ratio is not None
                    else None,
                    role="planning_only_no_precision_guarantee",
                )
            )
    pd.DataFrame(rows).to_csv(output / "MC_budget_planning.csv", index=False)
    conditional = []
    diagnostics = []
    for cell in config["gamm"]["cells"]:
        cid = cell["id"]
        replicates = []
        for e in sorted(records.values(), key=lambda e: e["payload"]["task"]):
            p = e["payload"]
            if p["job"]["stage"] == "gamm" and p["job"]["cell"]["id"] == cid:
                result = p["result"]
                if result["status"] != "batch_completed":
                    raise ValueError("Unexpected pilot batch failure")
                replicates += result["replicates"]
        if len(replicates) != config["gamm"]["replicates"]:
            raise ValueError("Missing pilot replicates")
        for flag in [False, True]:
            subset = [
                r
                for r in replicates
                if r["status"] == "estimated" and r["diagnostics"]["apVar_ok"] == flag
            ]
            if not subset:
                continue
            curve = np.asarray([r["curve"] for r in subset])
            q = np.quantile(curve, [0.025, 0.5, 0.975], axis=0, method="inverted_cdf")
            for i in range(cell["end"]):
                conditional.append(
                    dict(
                        cell=cid,
                        apVar_finite_matrix=flag,
                        n=len(subset),
                        minute=i + 1,
                        lower=q[0, i],
                        median=q[1, i],
                        upper=q[2, i],
                        role="post_fit_conditional_descriptive_only",
                    )
                )
            for metric in ["rho", "edf", "residual_adjacent_correlation"]:
                values = [
                    r["diagnostics"][metric]
                    for r in subset
                    if r["diagnostics"][metric] is not None
                ]
                diagnostics.append(
                    dict(
                        cell=cid,
                        apVar_finite_matrix=flag,
                        n=len(subset),
                        metric=metric,
                        finite_n=len(values),
                        quantiles=np.quantile(
                            values, [0, 0.025, 0.5, 0.975, 1]
                        ).tolist()
                        if values
                        else None,
                        apVar_messages=dict(
                            collections.Counter(
                                r["diagnostics"]["apVar_detail"] for r in subset
                            )
                        ),
                        role="post_fit_conditional_descriptive_only",
                    )
                )
    pd.DataFrame(conditional).to_csv(
        output / "GAMM_conditional_curves.csv", index=False
    )
    write_new(output / "GAMM_conditional_diagnostics.json", diagnostics)
    if refit:
        data = json.loads((pilot / "private_inputs/data.json").read_bytes())
        if sha(pilot / "private_inputs/data.json") != frozen["private_data_sha256"]:
            raise ValueError("Private pilot input changed")
        assets = {
            n: (pilot / "snapshot" / n).read_bytes() for n in frozen["R_assets_sha256"]
        }
        # execute_r's fixed remote entry name is explicitly aliased to the new
        # diagnostic source in this separate frozen task; old backend stays intact.
        assets["R/distributed_vas_backend.R"] = (
            output / "snapshot/R/gamm_diagnostics_backend.R"
        ).read_bytes()
        asset_hashes = {n: sha_bytes(b) for n, b in assets.items()}
        write_new(
            output / "R_assets_manifest.json",
            dict(
                hashes=asset_hashes,
                entry_alias="R/distributed_vas_backend.R <- R/gamm_diagnostics_backend.R",
            ),
        )
        bundle = next(pilot.glob("capsaicin_R_*.zip"))
        package = bundle.stem
        sys.path.insert(0, str(bundle))
        module = importlib.import_module(package + ".distributed_r")
        with Client(scheduler, set_as_default=False) as client:
            ready = preflight(client, config)
            workers = ready["selected_workers"]
            if not workers or any(client.processing(workers=workers).values()):
                raise RuntimeError("No idle qualified R workers")
            lock = (pilot / "snapshot" / config["python_lock"]).read_text()
            env = client.run(portable(python_environment), lock, workers=workers)
            if any(env.values()):
                raise ValueError("Python lock mismatch")
            name = bundle.stem + "_" + sha(bundle)[:16] + ".zip"
            client.run_on_scheduler(
                portable(install), bundle.read_bytes(), sha(bundle), name
            )
            client.run(
                portable(install),
                bundle.read_bytes(),
                sha(bundle),
                name,
                workers=workers,
            )
            write_new(
                output / "worker_environment.json",
                dict(readiness=ready, Python_lock_issues=env),
            )
            # Exercise the new diagnostic serializer before touching real frames.
            rng = np.random.default_rng(84620)
            n = 40
            grid = np.arange(1, 21)
            y = (
                2
                + 0.15 * grid[None, :]
                + rng.normal(0, 0.5, (n, 1))
                + rng.normal(0, 0.12, (n, 20))
            )
            synthetic = dict(
                person=np.repeat([f"synthetic_{i}" for i in range(n)], 20).tolist(),
                time=np.tile(grid, n).tolist(),
                vas=y.reshape(-1).tolist(),
            )
            qa = []
            for correlated in [False, True]:
                request = dict(
                    task="synthetic_diagnostic_serializer_" + str(correlated),
                    seed=84620,
                    data=synthetic,
                    grid=grid.tolist(),
                    k=6,
                    correlated=correlated,
                )
                f = client.submit(
                    module.execute_r,
                    config["runtime"],
                    assets,
                    asset_hashes,
                    request,
                    workers=workers,
                    allow_other_workers=False,
                    pure=False,
                    retries=0,
                )
                result = f.result(timeout=200)
                f.release()
                if result["result"]["status"] != "estimated":
                    raise ValueError("Synthetic diagnostic fit failed")
                qa.append(result)
            write_new(output / "synthetic_diagnostic_QA.json", qa)
            comparisons = []
            for j in frozen["jobs"]:
                if j["stage"] != "reference" or j["cell"]["module"] != "gamm":
                    continue
                request = request_for(config, data, j)
                cid = j["cell"]["id"]
                f = client.submit(
                    module.execute_r,
                    config["runtime"],
                    assets,
                    asset_hashes,
                    request,
                    workers=workers,
                    allow_other_workers=False,
                    pure=False,
                    retries=0,
                )
                r = f.result(timeout=config["runtime"]["timeout_seconds"] + 30)
                f.release()
                write_new(output / ("reference_diagnostics__" + cid + ".json"), r)
                actual = r["result"]
                previous = records[j["id"]]["payload"]["result"]
                ok = actual["status"] == "estimated"
                comparisons.append(
                    dict(
                        cell=cid,
                        status=actual["status"],
                        same_reference_curve_strict=bool(
                            ok
                            and np.allclose(
                                actual["curve"], previous["curve"], rtol=1e-8, atol=1e-9
                            )
                        ),
                        max_absolute_curve_difference=float(
                            np.max(
                                np.abs(np.asarray(actual["curve"]) - previous["curve"])
                            )
                        )
                        if ok
                        else None,
                    )
                )
            write_new(output / "reference_comparison.json", comparisons)
    # Detect accidental edits to the completed pilot after diagnostic work.
    for name, h in completion["outputs_sha256"].items():
        if sha(pilot / name) != h:
            raise ValueError("Pilot changed during followup")
    write_new(
        output / "completion.json",
        dict(
            status="completed_readonly_pilot_diagnostics",
            reference_refits=refit,
            pilot_preserved=True,
            outputs_sha256={p.name: sha(p) for p in output.iterdir() if p.is_file()},
            primary_p_q=None,
        ),
    )
    print(
        json.dumps(
            dict(
                output=str(output),
                MC_statistics=len(rows),
                conditional_curve_rows=len(conditional),
                reference_refits=refit,
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pilot", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--refit", action="store_true")
    p.add_argument("--scheduler", default="tcp://192.0.2.54:8786")
    a = p.parse_args()
    diagnose(a.pilot.resolve(), a.output.resolve(), a.refit, a.scheduler)
