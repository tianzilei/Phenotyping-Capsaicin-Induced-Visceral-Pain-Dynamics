"""Persistent observed variability and complete-interval burden resampling."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
import zipfile

import numpy as np
import pandas as pd
from distributed import Client
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from run_dask_derivative_development import (
    sha,
    write_new,
    publish,
    recover,
    compare_payloads,
)
from capsaicin.distributed_development import canonical, digest
from capsaicin.distributed_observation import tokens_to_arrays, summarize_column
from capsaicin.distributed_variability import prepare_matrix, specifications


def prepare(config_path):
    cfg = json.loads(config_path.read_bytes())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (
        Path.home()
        / ".local/share/capsaicin-dask/runs"
        / f"dask_variability_bootstrap_{stamp}_{uuid.uuid4().hex[:8]}"
    )
    for folder in ("results", "snapshot", "private_inputs"):
        (out / folder).mkdir(parents=True)
    source = ROOT / cfg["source"]
    manifest = ROOT / cfg["source_manifest"]
    expected = json.loads(manifest.read_bytes())["outputs_sha256"][source.name]
    if sha(source) != expected:
        raise ValueError("Current person source hash mismatch")
    with (out / "private_inputs/people_source.csv").open("xb") as f:
        f.write(source.read_bytes())
    frame = pd.read_csv(
        out / "private_inputs/people_source.csv", dtype=str, keep_default_na=False
    )
    if len(frame) != cfg["expected_people"] or frame.ID.duplicated().any():
        raise ValueError("Invalid true-person cohort")
    values, _ = tokens_to_arrays(
        frame[[f"VAS_{m}min" for m in range(1, 21)]].to_numpy()
    )
    for key, n in cfg["expected_complete"].items():
        a, b = map(int, key.split("_"))
        if int(np.isfinite(values[:, a - 1 : b]).all(axis=1).sum()) != n:
            raise ValueError("Complete support changed")
    matrix = prepare_matrix(values, cfg)
    stage = "U06_variability"
    with (out / "private_inputs" / (stage + ".npz")).open("xb") as f:
        np.savez(f, a0=matrix)
    cfg["sequence"] = [stage]
    cfg["prepared_input_sha256"] = {
        stage: sha(out / "private_inputs" / (stage + ".npz"))
    }
    if len(specifications(cfg)) != cfg["statistic_family_size"]:
        raise ValueError("Wrong frozen MC family")
    sources = [
        config_path,
        Path(__file__),
        ROOT / "scripts/run_dask_derivative_development.py",
        ROOT / "src/capsaicin/distributed_variability.py",
        ROOT / "src/capsaicin/distributed_observation.py",
        ROOT / "src/capsaicin/distributed_development.py",
        ROOT / "src/capsaicin/variability.py",
        ROOT / "R/remaining_descriptives.R",
        ROOT / "config/variability_followup_v1.json",
        ROOT / "config/remaining_analysis_v1.json",
        ROOT / cfg["runtime_lock"],
        ROOT / cfg["parent"],
    ]
    code_hashes = {}
    for path in sources:
        target = out / "snapshot" / path.name
        with target.open("xb") as f:
            f.write(path.read_bytes())
        code_hashes[path.name] = sha(target)
    package = "capsaicin_variability_" + digest(code_hashes)[:16]
    bundle = out / (package + ".zip")
    with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(package + "/__init__.py", "")
        for name in (
            "distributed_variability.py",
            "distributed_observation.py",
            "distributed_development.py",
            "variability.py",
        ):
            z.write(out / "snapshot" / name, package + "/" + name)
    write_new(
        out / "run_manifest.json",
        dict(
            created_utc=datetime.now(timezone.utc).isoformat(),
            config=cfg,
            config_sha256=digest(cfg),
            input_sha256={
                cfg["source"]: expected,
                cfg["source_manifest"]: sha(manifest),
            },
            code_sha256=code_hashes,
            package=package,
            bundle=bundle.name,
            bundle_sha256=sha(bundle),
            git_revision=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            dirty_diff_sha256=hashlib.sha256(
                subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT)
            ).hexdigest(),
            scope="U06_observed_descriptive_person_resampling_no_new_scientific_tests",
        ),
    )
    print(
        json.dumps({"run_directory": str(out), "sequence": cfg["sequence"]}), flush=True
    )
    return out


def install_bundle(data, expected, name, dask_worker=None, dask_scheduler=None):
    import hashlib
    import sys
    import importlib
    from pathlib import Path

    service = dask_worker if dask_worker is not None else dask_scheduler
    path = Path(service.local_directory) / name
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Remote bundle hash collision")
    else:
        with path.open("xb") as f:
            f.write(data)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("Remote bundle corrupted")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    importlib.invalidate_caches()
    return dict(path=str(path), sha256=expected)


def reachable_workers(addresses):
    import socket
    from concurrent.futures import ThreadPoolExecutor

    def probe(a):
        host, port = a.split("://", 1)[1].rsplit(":", 1)
        try:
            with socket.create_connection((host, int(port)), timeout=1):
                pass
            return a, True
        except OSError:
            return a, False

    with ThreadPoolExecutor(max_workers=16) as pool:
        return dict(pool.map(probe, addresses))


def run(out, scheduler):
    state = json.loads((out / "run_manifest.json").read_bytes())
    cfg = state["config"]
    for name, expected in state["code_sha256"].items():
        if sha(out / "snapshot" / name) != expected:
            raise ValueError("Frozen code/config changed")
    for file in (Path(__file__), ROOT / "scripts/run_dask_derivative_development.py"):
        if sha(file) != state["code_sha256"][file.name]:
            raise ValueError("Driver revision changed")
    bundle = out / state["bundle"]
    if sha(bundle) != state["bundle_sha256"]:
        raise ValueError("Worker bundle changed")
    inputs = {}
    for stage in cfg["sequence"]:
        p = out / "private_inputs" / (stage + ".npz")
        if sha(p) != cfg["prepared_input_sha256"][stage]:
            raise ValueError("Prepared input changed")
        with np.load(p, allow_pickle=False) as f:
            inputs[stage] = tuple(f[k] for k in sorted(f.files))
    if len(specifications(cfg)) != cfg["statistic_family_size"]:
        raise ValueError("MC family allocation does not match statistic family")
    lockfile = out / "driver.lock"
    if lockfile.exists():
        prev = json.loads(lockfile.read_bytes())
        if (
            psutil.pid_exists(prev["pid"])
            and abs(psutil.Process(prev["pid"]).create_time() - prev["created"]) < 0.01
        ):
            raise ValueError("Another driver is active")
        lockfile.unlink()
    write_new(
        lockfile, dict(pid=psutil.Process().pid, created=psutil.Process().create_time())
    )
    records = recover(out)
    sys.path.insert(0, str(bundle))

    def validate_record(key, item):
        p = item["payload"]
        stage = p["stage"]
        if (
            p["config_sha256"] != state["config_sha256"]
            or stage not in cfg["sequence"]
            or p["input_sha256"] != cfg["prepared_input_sha256"][stage]
        ):
            raise ValueError("Checkpoint input or configuration mismatch")
        start, stop = p["start"], p["stop"]
        if (
            key != f"{stage}__{start:05d}"
            or start % cfg["batch_size"]
            or stop != min(start + cfg["batch_size"], cfg["replicates"])
            or not 0 <= start < stop <= cfg["replicates"]
        ):
            raise ValueError("Checkpoint replicate extent mismatch")
        if (
            len(p["statistics"]) != stop - start
            or len(p["index_sha256"]) != stop - start
            or any(len(row) != cfg["statistic_family_size"] for row in p["statistics"])
        ):
            raise ValueError("Checkpoint dimensions mismatch")

    for key, item in records.items():
        validate_record(key, item)
    module = importlib.import_module(state["package"] + ".distributed_variability")
    env_module = importlib.import_module(state["package"] + ".distributed_development")
    lock = (out / "snapshot" / Path(cfg["runtime_lock"]).name).read_text()
    client = Client(scheduler, set_as_default=False, timeout="30s")
    qualified = {}
    last_refresh = 0.0
    started = time.monotonic()
    seq = len(list(out.glob("progress_*.json")))

    def refresh():
        nonlocal last_refresh, qualified
        if time.monotonic() - last_refresh < 5:
            return
        info = client.scheduler_info()["workers"]
        ports = reachable_workers(info)
        new = sorted(a for a in set(info) - set(qualified) if ports[a])
        if new:
            delivery = client.run(
                install_bundle,
                bundle.read_bytes(),
                sha(bundle),
                bundle.name,
                workers=new,
            )
            write_new(out / ("bundle_delivery_" + uuid.uuid4().hex + ".json"), delivery)
            checks = client.run(env_module.environment, lock, workers=new)
            write_new(
                out / ("worker_environment_" + uuid.uuid4().hex + ".json"), checks
            )
            for a, q in checks.items():
                host = a.split("://", 1)[1].split(":", 1)[0]
                if (
                    not q["issues"]
                    and info[a]["nthreads"] == 1
                    and info[a]["memory_limit"] >= 2 * 1024**3
                    and host != "192.0.2.54"
                ):
                    qualified[a] = q
        qualified = {a: q for a, q in qualified.items() if a in info and ports[a]}
        last_refresh = time.monotonic()

    def eligible():
        hosts = {}
        for a, q in qualified.items():
            hosts.setdefault(a.split("://", 1)[1].split(":", 1)[0], []).append(a)
        return [
            a
            for group in hosts.values()
            for a in sorted(group)[: qualified[group[0]]["physical_cores"]]
        ]

    def progress(stage, status, pending=0):
        nonlocal seq
        seq += 1
        value = dict(
            stage=stage,
            status=status,
            pid=psutil.Process().pid,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            completed_batches=len(records),
            pending=pending,
            workers=len(qualified),
            selected_workers=len(eligible()),
            replicates_per_stage=cfg["replicates"],
            run_directory=str(out),
        )
        write_new(out / f"progress_{seq:06d}.json", value)
        print(json.dumps(value), flush=True)
        state_path = (
            Path.home()
            / ".local/share/capsaicin-dask/state/active-development-driver.json"
        )
        temporary = state_path.with_suffix(".tmp")
        temporary.write_bytes(canonical(value) + b"\n")
        temporary.replace(state_path)

    try:
        scheduler_delivery = client.run_on_scheduler(
            install_bundle, bundle.read_bytes(), sha(bundle), bundle.name
        )
        write_new(
            out / ("scheduler_bundle_delivery_" + uuid.uuid4().hex + ".json"),
            scheduler_delivery,
        )
        refresh()
        if not qualified:
            raise RuntimeError("No qualified remote workers")
        for stage in cfg["sequence"]:
            if (out / (stage + "_summary.json")).exists():
                continue
            data = inputs[stage]
            engineering = out / (stage + "_engineering.json")
            if not engineering.exists():
                one = module.bootstrap_batch(cfg, data, stage, 0, 20)
                for worker in eligible():
                    check = client.submit(
                        module.bootstrap_batch,
                        cfg,
                        data,
                        stage,
                        0,
                        20,
                        workers=[worker],
                        allow_other_workers=False,
                        pure=False,
                        retries=0,
                    )
                    remote = check.result(timeout=60)
                    compare_payloads(one["payload"], remote["payload"], 1e-9, 1e-10)
                    check.release()
                chunks = [
                    client.submit(
                        module.bootstrap_batch,
                        cfg,
                        data,
                        stage,
                        a,
                        b,
                        workers=eligible(),
                        allow_other_workers=False,
                        pure=False,
                        retries=0,
                    )
                    for a, b in [(10, 20), (0, 10)]
                ]
                parts = client.gather(chunks)
                parts.sort(key=lambda x: x["payload"]["start"])
                merged = sum((x["payload"]["statistics"] for x in parts), [])
                hashes = sum((x["payload"]["index_sha256"] for x in parts), [])
                if hashes != one["payload"]["index_sha256"]:
                    raise ValueError("Batch-dependent random subject indices")
                compare_payloads(one["payload"]["statistics"], merged, 1e-9, 1e-10)
                for f in chunks:
                    f.release()
                write_new(
                    engineering,
                    dict(
                        status="PASS",
                        serial_vs_reordered_batches="PASS",
                        replicates=20,
                        index_hash="exact",
                        rtol=1e-9,
                        atol=1e-10,
                        real_input_scope="fixed_descriptive_no_new_tests",
                        worker_addresses=eligible(),
                        local_serial_vs_each_selected_worker="PASS",
                    ),
                )
            tasks = [
                (a, min(a + cfg["batch_size"], cfg["replicates"]))
                for a in range(0, cfg["replicates"], cfg["batch_size"])
                if f"{stage}__{a:05d}" not in records
            ]
            pending = {}
            index = 0
            last_report = 0.0
            progress(stage, "running")
            while index < len(tasks) or pending:
                if time.monotonic() - started > cfg["driver_timeout_seconds"]:
                    raise TimeoutError("Frozen driver timeout")
                refresh()
                workers = eligible()
                while index < len(tasks) and len(pending) < len(workers):
                    a, b = tasks[index]
                    index += 1
                    f = client.submit(
                        module.bootstrap_batch,
                        cfg,
                        data,
                        stage,
                        a,
                        b,
                        workers=workers,
                        allow_other_workers=False,
                        pure=False,
                        retries=0,
                    )
                    pending[f] = f"{stage}__{a:05d}"
                for f in [x for x in pending if x.done()]:
                    key = pending.pop(f)
                    item = f.result()
                    validate_record(key, item)
                    h = publish(out / "results" / (key + ".json"), item)
                    with (out / "checkpoint_journal.jsonl").open("ab") as handle:
                        handle.write(canonical(dict(task=key, file_sha256=h)) + b"\n")
                        handle.flush()
                        import os

                        os.fsync(handle.fileno())
                    records[key] = json.loads(
                        (out / "results" / (key + ".json")).read_bytes()
                    )
                    f.release()
                if time.monotonic() - last_report > 10:
                    progress(
                        stage,
                        "running" if workers else "waiting_for_qualified_worker",
                        len(pending),
                    )
                    last_report = time.monotonic()
                time.sleep(0.05 if workers else 1.0)
            selected = sorted(
                [
                    v["payload"]
                    for v in records.values()
                    if v["payload"]["stage"] == stage
                ],
                key=lambda x: x["start"],
            )
            values = np.asarray(
                sum((v["statistics"] for v in selected), []), dtype=float
            )
            if len(values) != cfg["replicates"]:
                raise ValueError("Missing bootstrap replicates")
            summary = []
            for j, spec in enumerate(specifications(cfg)):
                row = summarize_column(values[:, j], cfg, spec["bounds"], spec["unit"])
                mc = row.get("MC_max_endpoint_half_width")
                if row.get("valid", 0):
                    width = row["empirical_range_width"]
                    relative = mc is not None and (
                        mc <= 0.02 * width if width else mc == 0
                    )
                    row["status"] = (
                        "MC_PRECISION_MET"
                        if relative and mc <= spec["MC_absolute_tolerance"]
                        else "MC_PRECISION_INSUFFICIENT"
                    )
                row.update(
                    **spec,
                    point=selected[0]["point"][j],
                    original_eligible_people=selected[0]["original_eligible_counts"][j],
                    resampled_support_min=min(
                        p["resampled_support_min"][j] for p in selected
                    ),
                    resampled_support_max=max(
                        p["resampled_support_max"][j] for p in selected
                    ),
                )
                summary.append(row)
            write_new(out / (stage + "_summary.json"), summary)
            progress(stage, "stage_completed")
        # Source files must remain unchanged even though analysis uses frozen private copies.
        for path, expected in state["input_sha256"].items():
            if sha(ROOT / path) != expected:
                raise ValueError("Source mutated during resampling")
        if not (out / "completion.json").exists():
            write_new(
                out / "completion.json",
                dict(
                    status="completed_descriptive_resampling",
                    real_primary_tests_executed=False,
                    completed_utc=datetime.now(timezone.utc).isoformat(),
                    batches=len(records),
                    outputs_sha256={
                        p.name: sha(p)
                        for p in out.iterdir()
                        if p.is_file() and p.name != "driver.lock"
                    },
                    not_completed=cfg["not_in_this_batch"],
                ),
            )
        progress("all", "completed_descriptive_resampling")
    except Exception as exc:
        progress("execution", "failed")
        write_new(out / ("error_" + uuid.uuid4().hex + ".json"), dict(error=repr(exc)))
        raise
    finally:
        client.close()
        lockfile.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/dask_variability_bootstrap_20261003_v1.json",
    )
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--scheduler", default="tcp://192.0.2.54:8786")
    args = parser.parse_args()
    out = args.resume.resolve() if args.resume else prepare(args.config.resolve())
    run(out, args.scheduler)


if __name__ == "__main__":
    main()
