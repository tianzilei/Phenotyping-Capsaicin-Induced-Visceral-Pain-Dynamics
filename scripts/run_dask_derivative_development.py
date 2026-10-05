"""Persistent driver for frozen synthetic development on qualified remote workers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import zipfile

from distributed import Client, wait
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.distributed_development import canonical, digest


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open("xb") as handle:
        handle.write(canonical(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def publish(path, envelope):
    """No-overwrite publish; duplicate execution must have the same payload."""
    if digest(envelope["payload"]) != envelope["payload_sha256"]:
        raise ValueError("Payload hash mismatch")
    temp = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    write_new(temp, envelope)
    try:
        try:
            os.link(temp, path)
        except FileExistsError:
            prior = json.loads(path.read_bytes())
            if digest(prior["payload"]) != prior["payload_sha256"]:
                raise ValueError("Existing checkpoint payload corrupted")
            if prior["payload_sha256"] != envelope["payload_sha256"]:
                raise ValueError(
                    "Conflicting duplicate result; prior artifact preserved"
                )
    finally:
        temp.unlink()
    return sha(path)


def recover(out):
    records = {}
    journal = out / "checkpoint_journal.jsonl"
    if journal.exists():
        lines = journal.read_bytes().splitlines(keepends=True)
        for i, line in enumerate(lines):
            # A hard crash may leave one incomplete final append; preserve it as evidence.
            if not line.endswith(b"\n") and i == len(lines) - 1:
                raise ValueError(
                    "Incomplete journal append; retained for explicit repair"
                )
            entry = json.loads(line)
            path = out / "results" / (entry["task"] + ".json")
            if sha(path) != entry["file_sha256"]:
                raise ValueError("Checkpoint file hash mismatch: " + entry["task"])
            item = json.loads(path.read_bytes())
            if digest(item["payload"]) != item["payload_sha256"]:
                raise ValueError("Checkpoint payload hash mismatch")
            if entry["task"] in records:
                raise ValueError("Duplicate checkpoint journal key")
            records[entry["task"]] = item
    return records


def task_id(cell, stage, replicate):
    return f"{stage}__{cell['id']}__{replicate:05d}"


def compare_payloads(a, b, rtol, atol):
    """Discrete values and input hashes exact; finite floats use frozen tolerance."""
    if type(a) is not type(b):
        raise ValueError("Payload types differ")
    if isinstance(a, dict):
        if a.keys() != b.keys():
            raise ValueError("Payload fields differ")
        for k in a:
            compare_payloads(a[k], b[k], rtol, atol)
    elif isinstance(a, list):
        if len(a) != len(b):
            raise ValueError("Payload lengths differ")
        for x, y in zip(a, b):
            compare_payloads(x, y, rtol, atol)
    elif isinstance(a, float):
        if abs(a - b) > atol + rtol * abs(a):
            raise ValueError("Numerical equivalence tolerance exceeded")
    elif a != b:
        raise ValueError("Discrete values or logical input hashes differ")


def summarize(config, records, stage):
    from scipy.stats import norm

    z = float(norm.ppf(0.975))

    def wilson(k, n):
        p = k / n
        den = 1 + z * z / n
        center = (p + z * z / (2 * n)) / den
        half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
        return center - half, center + half

    rows = []
    for cell in config["cells"]:
        vals = [
            r["payload"]
            for r in records.values()
            if r["payload"]["stage"] == stage and r["payload"]["cell"] == cell["id"]
        ]
        valid = [v for v in vals if v["success"]]
        n, success = len(vals), len(valid)
        k = sum(v["projection_covered"] for v in vals)
        lo, hi = wilson(k, n)
        row = dict(
            cell=cell["id"],
            truth_role=cell["truth_role"],
            attempted=n,
            successes=success,
            failures=n - success,
            projection_coverage=k / n,
            coverage_MC_lower=lo,
            coverage_MC_upper=hi,
            analytic_coverage=sum(v["analytic_covered"] for v in vals) / n,
            mean_width=sum(v["mean_width"] for v in valid) / success
            if success
            else None,
            boundary_width=sum(v["boundary_width"] for v in valid) / success
            if success
            else None,
            max_design_condition=max(v["design_condition"] for v in vals),
            minimum_observed_support=min(min(v["support"]) for v in vals),
            below_zero_or_above_ten=sum(v["outside_scale"] for v in vals),
            acceptance="NOT_ASSESSED_DEVELOPMENT_ONLY",
        )
        if cell["scenario"] == "flat_complete":
            reject = sum(v["flat_rejected"] for v in vals if v["success"])
            row.update(
                flat_rejection_lower=reject / n,
                flat_rejection_upper=(reject + n - success) / n,
            )
        rows.append(row)
    return rows


def new_run(config_path, output_base=None):
    config = json.loads(config_path.read_bytes())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if output_base is None:
        output_base = Path.home() / ".local/share/capsaicin-dask/runs"
    out = output_base / f"dask_derivative_development_{stamp}_{uuid.uuid4().hex[:8]}"
    (out / "results").mkdir(parents=True)
    (out / "snapshot").mkdir()
    # Fail before remote work if this filesystem cannot publish exclusively.
    probe = out / ".publication_probe"
    write_new(probe, {"synthetic": True})
    probe_link = out / ".publication_probe_link"
    try:
        os.link(probe, probe_link)
    finally:
        probe.unlink(missing_ok=True)
        probe_link.unlink(missing_ok=True)
    sources = [
        config_path,
        Path(__file__).resolve(),
        ROOT / "src/capsaicin/derivative_v5.py",
        ROOT / "src/capsaicin/distributed_development.py",
        ROOT / config["runtime_lock"],
        ROOT / config["parent"],
    ]
    hashes = {}
    for source in sources:
        destination = out / "snapshot" / source.name
        with destination.open("xb") as handle:
            handle.write(source.read_bytes())
        hashes[source.name] = sha(destination)
    package = "capsaicin_job_" + digest(hashes)[:16]
    bundle = out / (package + ".zip")
    with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(package + "/__init__.py", "")
        for name in ("derivative_v5.py", "distributed_development.py"):
            archive.write(out / "snapshot" / name, package + "/" + name)
    manifest = dict(
        created_utc=datetime.now(timezone.utc).isoformat(),
        scope="synthetic_derivative_development_only",
        config=config,
        config_sha256=digest(config),
        sources_sha256=hashes,
        bundle=bundle.name,
        bundle_sha256=sha(bundle),
        package=package,
        project_root=str(ROOT),
        code_revision=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        dirty_diff_sha256=hashlib.sha256(
            subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT)
        ).hexdigest(),
        real_participant_data=False,
        confirmation_can_start=False,
    )
    write_new(out / "run_manifest.json", manifest)
    print(
        json.dumps(
            {
                "run_directory": str(out),
                "planned_development": len(config["cells"])
                * config["development_per_cell"],
            }
        ),
        flush=True,
    )
    return out


def run(out, scheduler):
    manifest = json.loads((out / "run_manifest.json").read_bytes())
    config = manifest["config"]
    for name, expected in manifest["sources_sha256"].items():
        if sha(out / "snapshot" / name) != expected:
            raise ValueError("Frozen source changed: " + name)
    if sha(Path(__file__)) != manifest["sources_sha256"][Path(__file__).name]:
        raise ValueError("Driver differs from frozen source; use the matching revision")
    bundle = out / manifest["bundle"]
    if sha(bundle) != manifest["bundle_sha256"]:
        raise ValueError("Worker bundle changed")
    lock = (out / "snapshot" / Path(config["runtime_lock"]).name).read_text()
    driver_lock = out / "driver.lock"
    if driver_lock.exists():
        previous = json.loads(driver_lock.read_bytes())
        if psutil.pid_exists(previous["pid"]):
            process = psutil.Process(previous["pid"])
            if abs(process.create_time() - previous["created"]) < 0.01:
                raise ValueError("A driver is already using this run")
        driver_lock.unlink()
    write_new(
        driver_lock, dict(pid=os.getpid(), created=psutil.Process().create_time())
    )
    write_new(
        out / ("driver_session_" + uuid.uuid4().hex + ".json"),
        dict(
            pid=os.getpid(),
            started_utc=datetime.now(timezone.utc).isoformat(),
            scheduler=scheduler,
        ),
    )
    started = time.monotonic()
    progress_seq = len(list(out.glob("progress_*.json")))
    records = recover(out)
    sys.path.insert(0, str(bundle))
    module = importlib.import_module(manifest["package"] + ".distributed_development")
    client = Client(scheduler, set_as_default=False, timeout="30s")
    qualifications = {}
    last_refresh = 0.0

    def progress(status, stage, pending=0):
        nonlocal progress_seq
        progress_seq += 1
        value = dict(
            status=status,
            stage=stage,
            pid=os.getpid(),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            durable_completed=len(records),
            pending=pending,
            worker_count=len(qualifications),
            planned_smoke=len(config["cells"]) * config["smoke_per_cell"],
            planned_development=len(config["cells"]) * config["development_per_cell"],
        )
        write_new(out / f"progress_{progress_seq:06d}.json", value)
        print(json.dumps(value), flush=True)

    def refresh(force=False):
        nonlocal qualifications, last_refresh
        if not force and time.monotonic() - last_refresh < 5:
            return
        info = client.scheduler_info()["workers"]
        unknown = sorted(set(info) - set(qualifications))
        if unknown:
            client.upload_file(str(bundle))
            checks = client.run(module.environment, lock, workers=unknown)
            stamp = uuid.uuid4().hex
            write_new(out / ("worker_environment_" + stamp + ".json"), checks)
            for address, check in checks.items():
                if (
                    not check["issues"]
                    and info[address]["nthreads"] == 1
                    and info[address]["memory_limit"]
                    >= config["worker_minimum_memory_bytes"]
                    and address.split("://", 1)[1].split(":", 1)[0] != "192.0.2.54"
                ):
                    qualifications[address] = check
        qualifications = {a: q for a, q in qualifications.items() if a in info}
        last_refresh = time.monotonic()

    def commit(key, result):
        if result["payload"]["config_sha256"] != manifest["config_sha256"]:
            raise ValueError("Result has another frozen configuration")
        p = result["payload"]
        if task_id({"id": p["cell"]}, p["stage"], p["replicate"]) != key:
            raise ValueError("Task/result identity mismatch")
        file_hash = publish(out / "results" / (key + ".json"), result)
        with (out / "checkpoint_journal.jsonl").open("ab") as handle:
            handle.write(canonical(dict(task=key, file_sha256=file_hash)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        records[key] = json.loads((out / "results" / (key + ".json")).read_bytes())

    try:
        refresh(True)
        if not qualifications:
            raise RuntimeError("No qualified remote workers; no local worker created")
        for key, value in records.items():
            if value["payload"]["config_sha256"] != manifest["config_sha256"]:
                raise ValueError("Checkpoint configuration changed")
        engineering = out / "engineering_checks.json"
        if not engineering.exists():
            tasks = [(cell, "smoke", i) for cell in config["cells"] for i in range(2)]
            worker = sorted(qualifications)[0]
            # Serial reference executes remotely; the Mac remains a driver/scheduler.
            serial = client.submit(
                module.execute_serial,
                config,
                tasks,
                workers=[worker],
                allow_other_workers=False,
                pure=False,
                retries=0,
            ).result(timeout=300)
            parallel = client.map(
                module.execute,
                [config] * len(tasks),
                [t[0] for t in tasks],
                [t[1] for t in tasks],
                [t[2] for t in tasks],
                workers=list(qualifications),
                allow_other_workers=False,
                pure=False,
                retries=0,
            )
            values = client.gather(parallel)
            for task, a, b in zip(tasks, serial, values):
                compare_payloads(
                    a["payload"],
                    b["payload"],
                    config["engineering_tolerance"]["rtol"],
                    config["engineering_tolerance"]["atol"],
                )
                commit(task_id(*task), b)
            for future in parallel:
                future.release()
            # Close and reconnect a real Client, then recover durable records independently.
            client.close()
            client = Client(scheduler, set_as_default=False, timeout="30s")
            recovered = recover(out)
            if set(recovered) != set(records):
                raise ValueError("Checkpoint/client reconnect lost results")
            duplicate = client.submit(
                module.execute,
                config,
                *tasks[0],
                workers=[worker],
                allow_other_workers=False,
                pure=False,
                retries=0,
            ).result(timeout=60)
            first = out / "results" / (task_id(*tasks[0]) + ".json")
            before = sha(first)
            publish(first, duplicate)
            if sha(first) != before:
                raise ValueError("Duplicate publication changed an existing result")
            write_new(
                engineering,
                dict(
                    status="PASS",
                    serial_parallel_replicates=len(tasks),
                    serial_execution="remote_worker",
                    client_reconnect_resume="PASS",
                    duplicate_exclusive_publication="PASS",
                    input_hashes="exact",
                    numerical_tolerance=config["engineering_tolerance"],
                    actual_worker_kill_tested=False,
                    scheduler_restart_tested=False,
                    process_loss_scope="not_tested_no_scientific_readiness_claim",
                ),
            )
        for stage, count in (
            ("smoke", config["smoke_per_cell"]),
            ("development", config["development_per_cell"]),
        ):
            tasks = [
                (cell, stage, i)
                for i in range(count)
                for cell in config["cells"]
                if task_id(cell, stage, i) not in records
            ]
            pending, index = {}, 0
            last_progress = 0.0
            progress("running", stage)
            while index < len(tasks) or pending:
                if time.monotonic() - started > config["driver_timeout_seconds"]:
                    raise TimeoutError(
                        "Frozen driver timeout reached; durable records retained"
                    )
                refresh()
                hosts = {}
                for address, check in qualifications.items():
                    host = address.split("://", 1)[1].split(":", 1)[0]
                    hosts.setdefault(host, []).append(address)
                eligible = []
                for host, addresses in hosts.items():
                    addresses.sort()
                    cores = qualifications[addresses[0]]["physical_cores"]
                    eligible.extend(addresses[:cores])
                capacity = len(eligible)
                while index < len(tasks) and len(pending) < capacity:
                    task = tasks[index]
                    index += 1
                    f = client.submit(
                        module.execute,
                        config,
                        *task,
                        workers=eligible,
                        allow_other_workers=False,
                        pure=False,
                        retries=0,
                    )
                    pending[f] = task_id(*task)
                if pending:
                    done = [f for f in pending if f.done()]
                    for f in done:
                        key = pending.pop(f)
                        commit(key, f.result())
                        f.release()
                if time.monotonic() - last_progress > 10:
                    progress(
                        "running" if capacity else "waiting_for_qualified_worker",
                        stage,
                        len(pending),
                    )
                    last_progress = time.monotonic()
                time.sleep(0.05 if capacity else 1.0)
            rows = summarize(config, records, stage)
            summary = out / (stage + "_summary.json")
            if not summary.exists():
                write_new(summary, rows)
            progress("stage_completed", stage)
        write_new(
            out / "completion.json",
            dict(
                status="completed_development_only",
                completed_utc=datetime.now(timezone.utc).isoformat(),
                durable_completed=len(records),
                real_data_processed=False,
                confirmation_can_start=False,
                outputs_sha256={
                    p.name: sha(p)
                    for p in out.iterdir()
                    if p.is_file() and p.name != "driver.lock"
                },
                next_stage="real_VAS_and_prediction_require_separate_frozen_adapters",
            ),
        )
        progress("completed_development_only", "development")
    except Exception as exc:
        progress("failed", "execution")
        write_new(
            out / ("error_" + uuid.uuid4().hex + ".json"),
            dict(
                error_type=type(exc).__name__,
                error=str(exc),
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
            ),
        )
        raise
    finally:
        client.close()
        driver_lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/dask_derivative_development_20261003_v1.json",
    )
    parser.add_argument("--resume", type=Path)
    parser.add_argument(
        "--output-base",
        type=Path,
        help="Hardlink-capable local directory; defaults to user runtime/runs",
    )
    parser.add_argument("--scheduler", default="tcp://192.0.2.54:8786")
    args = parser.parse_args()
    out = (
        args.resume.resolve()
        if args.resume
        else new_run(args.config.resolve(), args.output_base)
    )
    run(out, args.scheduler)


if __name__ == "__main__":
    main()
