"""Preflight or resume the frozen R queue. Default is preflight only."""

import argparse
import collections
import importlib
import json
import os
import socket
import sys
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import psutil
from distributed import Client

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from capsaicin.distributed_r import canonical, sha_bytes
from capsaicin.distributed_r_plan import request_for
from capsaicin.distributed_observation import summarize_column
from run_dask_derivative_development import recover, publish, write_new, sha


def install(data, expected, name, dask_worker=None, dask_scheduler=None):
    import hashlib
    import sys
    import importlib
    from pathlib import Path

    service = dask_worker if dask_worker is not None else dask_scheduler
    path = Path(service.local_directory) / name
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Bundle conflict")
    else:
        with path.open("xb") as h:
            h.write(data)
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    importlib.invalidate_caches()
    return str(path)


def python_environment(lock):
    import importlib.metadata as md
    import platform
    from packaging.requirements import Requirement

    issues = []
    for raw in lock.splitlines():
        line = raw.strip().rstrip("\\").strip()
        if not line or line.startswith(("#", "--")):
            continue
        req = Requirement(line)
        if req.marker and not req.marker.evaluate():
            continue
        try:
            version = md.version(req.name)
        except md.PackageNotFoundError:
            version = None
        if version is None or not req.specifier.contains(version):
            issues.append(req.name)
    if platform.python_version() != "3.12.13":
        issues.append("python")
    return issues


def preflight(client, config):
    info = client.scheduler_info()
    targets = [
        a
        for a, w in info["workers"].items()
        if a.startswith("tcp://" + config["runtime"]["host"] + ":")
        and w["nthreads"] == 1
        and w["memory_limit"] >= config["runtime"]["worker_memory_minimum"]
    ]

    def probe(a):
        h, p = a.removeprefix("tcp://").rsplit(":", 1)
        try:
            with socket.create_connection((h, int(p)), timeout=1):
                pass
            return a, True
        except OSError:
            return a, False

    with ThreadPoolExecutor(max_workers=16) as pool:
        ports = dict(pool.map(probe, targets))
    ready = sorted(a for a in targets if ports[a])[
        : config["runtime"]["host_concurrency"]
    ]
    return dict(
        status="transport_ready_R_QA_required" if ready else "BLOCKED_REMOTE_DATA_PORT",
        registered_host_workers=targets,
        ports=ports,
        selected_workers=ready,
        scheduler_only=not any(
            a.startswith("tcp://192.0.2.54:") for a in info["workers"]
        ),
    )


def summarize(out, config, jobs, records, stage):
    if stage == "reference":
        return
    cells = {j["cell"]["id"]: j["cell"] for j in jobs if j["stage"] == stage}
    summary = []
    for cid, cell in cells.items():
        selected = sorted(
            (
                r["payload"]
                for r in records.values()
                if r["payload"]["job"]["stage"] == stage
                and r["payload"]["job"]["cell"]["id"] == cid
            ),
            key=lambda r: r["task"],
        )
        if stage == "reconstruction":
            complete = []
            failures = 0
            spec = config["complete"]["reconstruction"]
            for repeat in range(spec["repeats"]):
                folds = [p for p in selected if p["job"]["repeat"] == repeat]
                if len(folds) != spec["folds"]:
                    raise ValueError("Missing reconstruction fold")
                if any(p["result"]["status"] != "estimated" for p in folds):
                    failures += 1
                    continue
                seen = []
                loss = []
                baseline = []
                for p in folds:
                    r = p["result"]
                    seen += r["test_rows"]
                    loss += r["rmse_k0_to_4"]
                    baseline += r["person_constant_rmse"]
                    if set(r["test_rows"]) & set(r["train_rows"]):
                        raise ValueError("Person leakage")
                if sorted(seen) != list(range(len(seen))):
                    raise ValueError("Incomplete OOF coverage")
                loss = np.asarray(loss, float)
                baseline = np.asarray(baseline, float)
                complete.append(
                    dict(
                        repeat=repeat,
                        mean_rmse=loss.mean(axis=0).tolist(),
                        person_constant_rmse=float(baseline.mean()),
                        paired_difference=(loss - baseline[:, None])
                        .mean(axis=0)
                        .tolist(),
                    )
                )
            summary.append(
                dict(
                    cell=cid,
                    complete_repeats=complete,
                    failed_or_incomplete_repeats=failures,
                    role="whole_curve_reconstruction_split_sensitivity_not_forecasting_or_population_CI",
                )
            )
            continue
        replicates = []
        for p in selected:
            r = p["result"]
            job = p["job"]
            n = job["stop"] - job["start"]
            rows = r["replicates"] if r["status"] == "batch_completed" else [r] * n
            if len(rows) != n:
                raise ValueError("Missing R replicate")
            replicates += rows
        attempted = config[stage]["replicates"]
        if len(replicates) != attempted:
            raise ValueError("Bootstrap roster incomplete")
        ok = [r for r in replicates if r["status"] == "estimated"]
        failures = attempted - len(ok)
        reasons = dict(
            collections.Counter(
                r.get("reason", "unknown")
                for r in replicates
                if r["status"] != "estimated"
            )
        )
        if stage == "gamm":
            specs = [("curve", cell["end"], [None, None], config["MC"]["VAS_absolute"])]
        else:
            specs = [
                ("cumulative_fve", 4, [0, 1], config["MC"]["proportion_absolute"]),
                ("angle_deg", 4, [0, 90], config["MC"]["angle_absolute_degrees"]),
            ]
            if stage == "complete":
                specs.append(
                    ("matched_inner", 4, [0, 1], config["MC"]["matched_inner_absolute"])
                )
        for metric, columns, bounds, absolute in specs:
            for column in range(columns):
                values = [r[metric][column] for r in ok]
                mc = summarize_column(
                    np.asarray(values, float),
                    dict(
                        MC_total_error_probability=config["MC"][
                            "total_error_per_module"
                        ],
                        statistic_family_size=config["MC"]["families"][stage],
                    ),
                    bounds,
                    "native_units",
                )
                half = mc.get("MC_max_endpoint_half_width")
                width = mc.get("empirical_range_width")
                met = (
                    half is not None
                    and width is not None
                    and half <= absolute
                    and (
                        half <= config["MC"]["relative_tolerance"] * width
                        if width
                        else half == 0
                    )
                )
                gate = (
                    len(ok)
                    >= config[stage].get("minimum_success_fraction", 0) * attempted
                    and len(ok) > 0
                )
                mc.update(
                    cell=cid,
                    metric=metric,
                    index=column + 1,
                    attempted=attempted,
                    failed=failures,
                    failure_reasons=reasons,
                    status="MC_PRECISION_MET" if met else "MC_PRECISION_INSUFFICIENT",
                    publication="success_conditional_descriptive_range"
                    if gate
                    else "WITHHELD_FAILURE_GATE",
                    role="exploratory_stability_no_nominal_coverage_validation",
                    primary_p=None,
                    primary_q=None,
                )
                if not gate:
                    mc["lower"] = None
                    mc["upper"] = None
                summary.append(mc)
    write_new(out / (stage + "_summary.json"), summary)


def run(out, execute=False, scheduler="tcp://192.0.2.54:8786"):
    frozen = json.loads((out / "run_manifest.json").read_bytes())
    config = frozen["config"]
    for name, h in frozen["snapshot_sha256"].items():
        if sha(out / "snapshot" / name) != h:
            raise ValueError("Frozen source/config corrupted")
    for name, h in frozen["input_sha256"].items():
        if sha(ROOT / name) != h:
            raise ValueError("Original input changed")
    if sha(out / "private_inputs/data.json") != frozen["private_data_sha256"]:
        raise ValueError("Private input changed")
    for name in [
        "scripts/run_dask_R_analysis.py",
        "src/capsaicin/distributed_r_plan.py",
        "src/capsaicin/distributed_observation.py",
        "scripts/run_dask_derivative_development.py",
        "src/capsaicin/distributed_development.py",
    ]:
        if sha(ROOT / name) != frozen["snapshot_sha256"][name]:
            raise ValueError("Driver changed after freeze")
    data = json.loads((out / "private_inputs/data.json").read_bytes())
    jobs = frozen["jobs"]
    with Client(scheduler, set_as_default=False) as client:
        readiness = preflight(client, config)
        write_new(out / ("preflight_" + uuid.uuid4().hex + ".json"), readiness)
        print(json.dumps(readiness), flush=True)
        if not execute or not readiness["selected_workers"]:
            return readiness
        lockfile = out / "driver.lock"
        if lockfile.exists():
            p = json.loads(lockfile.read_bytes())
            if (
                psutil.pid_exists(p["pid"])
                and abs(psutil.Process(p["pid"]).create_time() - p["created"]) < 0.01
            ):
                raise ValueError("Driver already active")
            lockfile.unlink()
        write_new(
            lockfile, dict(pid=os.getpid(), created=psutil.Process().create_time())
        )
        try:
            records = recover(out)
            roster = {j["id"]: j for j in jobs}
            for task, r in records.items():
                p = r["payload"]
                if (
                    task not in roster
                    or p["job"] != roster[task]
                    or p["config_sha256"] != frozen["config_sha256"]
                    or p["input_sha256"] != frozen["private_data_sha256"]
                ):
                    raise ValueError("Checkpoint configuration/input mismatch")
            assets = {
                name: (out / "snapshot" / name).read_bytes()
                for name in frozen["R_assets_sha256"]
            }
            package = (
                "capsaicin_R_"
                + sha(out / "snapshot/src/capsaicin/distributed_r.py")[:16]
            )
            bundle = out / (package + ".zip")
            if not bundle.exists():
                with zipfile.ZipFile(
                    bundle, "x", compression=zipfile.ZIP_DEFLATED
                ) as z:
                    for name, content in [
                        (package + "/__init__.py", b""),
                        (
                            package + "/distributed_r.py",
                            (
                                out / "snapshot/src/capsaicin/distributed_r.py"
                            ).read_bytes(),
                        ),
                    ]:
                        entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                        entry.compress_type = zipfile.ZIP_DEFLATED
                        z.writestr(entry, content)
            with zipfile.ZipFile(bundle) as z:
                if (
                    set(z.namelist())
                    != {package + "/__init__.py", package + "/distributed_r.py"}
                    or sha_bytes(z.read(package + "/distributed_r.py"))
                    != frozen["snapshot_sha256"]["src/capsaicin/distributed_r.py"]
                ):
                    raise ValueError("Frozen Python worker bundle corrupted")
            sys.path.insert(0, str(bundle))
            module = importlib.import_module(package + ".distributed_r")
            workers = readiness["selected_workers"]
            lock = (out / "snapshot" / config["python_lock"]).read_text()
            if any(client.processing(workers=workers).values()):
                raise RuntimeError("Selected R workers already have running tasks")
            environment = client.run(python_environment, lock, workers=workers)
            if any(environment.values()):
                raise ValueError("Python worker lock mismatch")
            # Earlier archives used wall-clock ZIP timestamps. Equal Python code
            # can therefore have different archive bytes; preserve all old bundles
            # and address the transport file by its actual archive hash.
            transport_name = bundle.stem + "_" + sha(bundle)[:16] + ".zip"
            client.run_on_scheduler(
                install, bundle.read_bytes(), sha(bundle), transport_name
            )
            client.run(
                install,
                bundle.read_bytes(),
                sha(bundle),
                transport_name,
                workers=workers,
            )
            qas = {}
            for worker in workers:
                f = client.submit(
                    module.execute_r,
                    config["runtime"],
                    assets,
                    frozen["R_assets_sha256"],
                    dict(task="synthetic_R_QA", kind="qa", seed=config["master_seed"]),
                    workers=[worker],
                    allow_other_workers=False,
                    pure=False,
                    retries=0,
                )
                q = f.result(timeout=200)
                f.release()
                if q["result"]["status"] != "PASS":
                    raise ValueError("R synthetic QA failed")
                qas[worker] = q
            write_new(out / ("worker_QA_" + uuid.uuid4().hex + ".json"), qas)
            for stage in config["sequence"]:
                summary = out / (stage + "_summary.json")
                if stage != "reference" and summary.exists():
                    continue
                tasks = [
                    j for j in jobs if j["stage"] == stage and j["id"] not in records
                ]
                pending = {}
                index = 0
                last = 0
                while index < len(tasks) or pending:
                    while index < len(tasks) and len(pending) < len(workers):
                        job = tasks[index]
                        index += 1
                        request = request_for(config, data, job)
                        f = client.submit(
                            module.execute_r,
                            config["runtime"],
                            assets,
                            frozen["R_assets_sha256"],
                            request,
                            workers=workers,
                            allow_other_workers=False,
                            pure=False,
                            retries=0,
                        )
                        pending[f] = job
                    for f in [f for f in pending if f.done()]:
                        job = pending.pop(f)
                        result = f.result()
                        f.release()
                        if result["task"] != job["id"]:
                            raise ValueError("Wrong R task result")
                        payload = dict(
                            task=job["id"],
                            job=job,
                            result=result["result"],
                            config_sha256=frozen["config_sha256"],
                            input_sha256=frozen["private_data_sha256"],
                            request_sha256=result["request_sha256"],
                        )
                        envelope = dict(
                            payload=payload,
                            payload_sha256=sha_bytes(canonical(payload)),
                            execution={
                                k: result[k]
                                for k in [
                                    "seconds",
                                    "peak_sampled_R_RSS",
                                    "stdout",
                                    "stderr",
                                ]
                            },
                        )
                        h = publish(out / "results" / (job["id"] + ".json"), envelope)
                        with (out / "checkpoint_journal.jsonl").open("ab") as handle:
                            handle.write(
                                canonical(dict(task=job["id"], file_sha256=h)) + b"\n"
                            )
                            handle.flush()
                            os.fsync(handle.fileno())
                        records[job["id"]] = envelope
                    if time.monotonic() - last > 15:
                        print(
                            json.dumps(
                                dict(
                                    stage=stage,
                                    completed=len(records),
                                    total=len(jobs),
                                    pending=len(pending),
                                )
                            ),
                            flush=True,
                        )
                        last = time.monotonic()
                    time.sleep(0.1)
                if stage == "reference" and any(
                    r["payload"]["result"]["status"] != "estimated"
                    for r in records.values()
                    if r["payload"]["job"]["stage"] == "reference"
                ):
                    raise RuntimeError(
                        "Reference estimator inestimable; artifacts retained, bootstrap not started"
                    )
                if stage != "reference" and not summary.exists():
                    summarize(out, config, jobs, records, stage)
            for name, h in frozen["input_sha256"].items():
                if sha(ROOT / name) != h:
                    raise ValueError("Original source changed during run")
            if not (out / "completion.json").exists():
                write_new(
                    out / "completion.json",
                    dict(
                        status="completed_exploratory_R_stability",
                        jobs=len(records),
                        primary_p_q=None,
                        sealed_people_used=0,
                        outputs_sha256={
                            p.name: sha(p)
                            for p in out.iterdir()
                            if p.is_file() and p.name != "driver.lock"
                        },
                    ),
                )
            return dict(status="completed_exploratory_R_stability", jobs=len(records))
        finally:
            lockfile.unlink(missing_ok=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--scheduler", default="tcp://192.0.2.54:8786")
    a = p.parse_args()
    run(a.run.resolve(), a.execute, a.scheduler)
