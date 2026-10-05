"""Persistent 20-repeat whole-person nested CV on qualified remote workers."""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import psutil
from distributed import Client

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
from capsaicin.distributed_observation import tokens_to_arrays
from capsaicin.distributed_prediction import prepare_arrays


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


def prepare(config_path):
    cfg = json.loads(config_path.read_bytes())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (
        Path.home()
        / ".local/share/capsaicin-dask/runs"
        / f"dask_prediction_repeats_{stamp}_{uuid.uuid4().hex[:8]}"
    )
    for name in ("snapshot", "private_inputs", "results"):
        (out / name).mkdir(parents=True)
    source = ROOT / cfg["source"]
    manifest = ROOT / cfg["source_manifest"]
    expected = json.loads(manifest.read_bytes())["outputs_sha256"][source.name]
    if sha(source) != expected:
        raise ValueError("Current source output hash mismatch")
    with (out / "private_inputs/people_source.csv").open("xb") as f:
        f.write(source.read_bytes())
    people = pd.read_csv(
        out / "private_inputs/people_source.csv", dtype=str, keep_default_na=False
    ).sort_values("ID")
    if len(people) != cfg["expected_people"] or people.ID.duplicated().any():
        raise ValueError("True-person support changed")
    values, _ = tokens_to_arrays(
        people[[f"VAS_{m}min" for m in range(1, 21)]].to_numpy()
    )
    cfg["prepared_input_sha256"] = {}
    for stage in cfg["sequence"]:
        arrays = prepare_arrays(values, stage)
        x, y, g, t = arrays
        if (
            len(y) != cfg["expected_support"][stage]["rows"]
            or len(np.unique(g)) != cfg["expected_support"][stage]["people"]
        ):
            raise ValueError("Future-rating support changed")
        file = out / "private_inputs" / (stage + ".npz")
        with file.open("xb") as f:
            np.savez(f, **{f"a{i}": a for i, a in enumerate(arrays)})
        cfg["prepared_input_sha256"][stage] = sha(file)
    paths = [
        config_path,
        Path(__file__),
        ROOT / "scripts/run_dask_derivative_development.py",
        ROOT / "src/capsaicin/distributed_prediction.py",
        ROOT / "src/capsaicin/distributed_observation.py",
        ROOT / "src/capsaicin/distributed_development.py",
        ROOT / "scripts/run_next_rating_20260926.py",
        ROOT / "scripts/run_reanalysis_descriptives.py",
        ROOT / cfg["runtime_lock"],
        ROOT / cfg["parent"],
        *[ROOT / n for n in cfg["legacy_configs"]],
    ]
    hashes = {}
    for path in paths:
        target = out / "snapshot" / path.name
        with target.open("xb") as f:
            f.write(path.read_bytes())
        hashes[path.name] = sha(target)
    package = "capsaicin_prediction_" + digest(hashes)[:16]
    bundle = out / (package + ".zip")
    with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(package + "/__init__.py", "")
        for name in (
            "distributed_prediction.py",
            "distributed_observation.py",
            "distributed_development.py",
        ):
            z.write(out / "snapshot" / name, package + "/" + name)
    write_new(
        out / "run_manifest.json",
        dict(
            config=cfg,
            config_sha256=digest(cfg),
            input_sha256={
                cfg["source"]: expected,
                cfg["source_manifest"]: sha(manifest),
            },
            code_sha256=hashes,
            package=package,
            bundle=bundle.name,
            bundle_sha256=sha(bundle),
            git_revision=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            dirty_diff_sha256=hashlib.sha256(
                subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT)
            ).hexdigest(),
            created_utc=datetime.now(timezone.utc).isoformat(),
            scope="two_future_rating_tasks_20_training_split_repeats_no_independent_fold_tests",
        ),
    )
    print(
        json.dumps(
            dict(
                run_directory=str(out), repeats=cfg["repeats"], sequence=cfg["sequence"]
            )
        ),
        flush=True,
    )
    return out


def key_for(stage, repeat, fold):
    return f"{stage}__repeat{repeat:03d}__fold{fold}"


def run(out, scheduler):
    state = json.loads((out / "run_manifest.json").read_bytes())
    cfg = state["config"]
    for name, expected in state["code_sha256"].items():
        if sha(out / "snapshot" / name) != expected:
            raise ValueError("Frozen snapshot changed")
    for file in (Path(__file__), ROOT / "scripts/run_dask_derivative_development.py"):
        if sha(file) != state["code_sha256"][file.name]:
            raise ValueError("Driver changed since freeze")
    bundle = out / state["bundle"]
    if sha(bundle) != state["bundle_sha256"]:
        raise ValueError("Worker bundle changed")
    inputs = {}
    for stage in cfg["sequence"]:
        file = out / "private_inputs" / (stage + ".npz")
        if sha(file) != cfg["prepared_input_sha256"][stage]:
            raise ValueError("Prepared input changed")
        with np.load(file, allow_pickle=False) as f:
            inputs[stage] = tuple(f[n] for n in sorted(f.files))
    lockfile = out / "driver.lock"
    if lockfile.exists():
        previous = json.loads(lockfile.read_bytes())
        if (
            psutil.pid_exists(previous["pid"])
            and abs(psutil.Process(previous["pid"]).create_time() - previous["created"])
            < 0.01
        ):
            raise ValueError("Another driver is active")
        lockfile.unlink()
    write_new(lockfile, dict(pid=os.getpid(), created=psutil.Process().create_time()))
    records = recover(out)
    sys.path.insert(0, str(bundle))
    module = importlib.import_module(state["package"] + ".distributed_prediction")
    environment = importlib.import_module(
        state["package"] + ".distributed_development"
    ).environment
    lock = (out / "snapshot" / Path(cfg["runtime_lock"]).name).read_text()

    def validate(key, item):
        p = item["payload"]
        stage = p["stage"]
        if (
            stage not in cfg["sequence"]
            or p["config_sha256"] != state["config_sha256"]
            or p["input_sha256"] != cfg["prepared_input_sha256"][stage]
        ):
            raise ValueError("Checkpoint source/config mismatch")
        if (
            not 0 <= p["repeat"] < cfg["repeats"]
            or not 0 <= p["fold"] < cfg["outer_folds"]
            or key != key_for(stage, p["repeat"], p["fold"])
        ):
            raise ValueError("Checkpoint task identity mismatch")

    for key, item in records.items():
        validate(key, item)
    client = Client(scheduler, set_as_default=False, timeout="30s")
    qualified = {}
    last_refresh = 0.0
    start = time.monotonic()
    seq = len(list(out.glob("progress_*.json")))

    def refresh():
        nonlocal last_refresh, qualified
        if time.monotonic() - last_refresh < 5:
            return
        workers = client.scheduler_info()["workers"]
        ports = reachable_workers(workers)
        new = sorted(
            a
            for a in set(workers) - set(qualified)
            if ports[a] and not a.startswith("tcp://192.0.2.54:")
        )
        if new:
            receipt = client.run(
                install_bundle,
                bundle.read_bytes(),
                sha(bundle),
                bundle.name,
                workers=new,
            )
            checks = client.run(environment, lock, workers=new)
            write_new(
                out / ("worker_environment_" + uuid.uuid4().hex + ".json"),
                dict(bundle_delivery=receipt, environment=checks),
            )
            for a, q in checks.items():
                if (
                    not q["issues"]
                    and workers[a]["nthreads"] == 1
                    and workers[a]["memory_limit"] >= 2 * 1024**3
                ):
                    qualified[a] = q
        qualified = {a: q for a, q in qualified.items() if a in workers and ports[a]}
        last_refresh = time.monotonic()

    def eligible():
        hosts = {}
        for a in qualified:
            hosts.setdefault(a.split("://", 1)[1].rsplit(":", 1)[0], []).append(a)
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
            pid=os.getpid(),
            run_directory=str(out),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            completed_folds=len(records),
            total_folds=len(cfg["sequence"]) * cfg["repeats"] * cfg["outer_folds"],
            pending=pending,
            selected_workers=len(eligible()),
        )
        write_new(out / f"progress_{seq:06d}.json", value)
        print(json.dumps(value), flush=True)
        path = (
            Path.home()
            / ".local/share/capsaicin-dask/state/active-development-driver.json"
        )
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(canonical(value) + b"\n")
        tmp.replace(path)

    try:
        scheduler_receipt = client.run_on_scheduler(
            install_bundle, bundle.read_bytes(), sha(bundle), bundle.name
        )
        if not (out / "scheduler_bundle_delivery.json").exists():
            write_new(out / "scheduler_bundle_delivery.json", scheduler_receipt)
        refresh()
        if not eligible():
            raise RuntimeError("No qualified remote workers")
        for stage in cfg["sequence"]:
            summary_path = out / (stage + "_repeat_summaries.json")
            if summary_path.exists():
                continue
            data = inputs[stage]
            qa = out / (stage + "_engineering.json")
            if not qa.exists():
                # Small synthetic training check; actual resampling/training runs on remote workers.
                synthetic = module.prepare_arrays(
                    np.random.default_rng(731).uniform(0, 10, (30, 20)), stage
                )
                qcfg = dict(
                    cfg,
                    forest_trees=3,
                    ridge_alpha=[1.0],
                    forest_depth=[2],
                    prepared_input_sha256={stage: "synthetic_fixture_only"},
                )
                local = module.execute_fold(qcfg, synthetic, stage, 0, 0)
                for a in eligible():
                    f = client.submit(
                        module.execute_fold,
                        qcfg,
                        synthetic,
                        stage,
                        0,
                        0,
                        workers=[a],
                        allow_other_workers=False,
                        pure=False,
                        retries=0,
                    )
                    remote = f.result(timeout=60)
                    compare_payloads(local["payload"], remote["payload"], 1e-9, 1e-10)
                    f.release()
                write_new(
                    qa,
                    dict(
                        status="PASS",
                        input_scope="synthetic_only",
                        local_serial_vs_every_selected_worker="PASS",
                        rtol=1e-9,
                        atol=1e-10,
                        workers=eligible(),
                        forest_trees=3,
                    ),
                )
            tasks = [
                (repeat, fold)
                for repeat in range(cfg["repeats"])
                for fold in range(cfg["outer_folds"])
                if key_for(stage, repeat, fold) not in records
            ]
            pending = {}
            index = 0
            last_report = 0.0
            progress(stage, "running")
            while index < len(tasks) or pending:
                if time.monotonic() - start > cfg["driver_timeout_seconds"]:
                    raise TimeoutError("Frozen driver timeout")
                refresh()
                workers = eligible()
                while index < len(tasks) and len(pending) < len(workers):
                    repeat, fold = tasks[index]
                    index += 1
                    future = client.submit(
                        module.execute_fold,
                        cfg,
                        data,
                        stage,
                        repeat,
                        fold,
                        workers=workers,
                        allow_other_workers=False,
                        pure=False,
                        retries=0,
                    )
                    pending[future] = key_for(stage, repeat, fold)
                for f in [f for f in pending if f.done()]:
                    key = pending.pop(f)
                    item = f.result()
                    validate(key, item)
                    h = publish(out / "results" / (key + ".json"), item)
                    with (out / "checkpoint_journal.jsonl").open("ab") as handle:
                        handle.write(canonical(dict(task=key, file_sha256=h)) + b"\n")
                        handle.flush()
                        os.fsync(handle.fileno())
                    records[key] = json.loads(
                        (out / "results" / (key + ".json")).read_bytes()
                    )
                    f.release()
                if time.monotonic() - last_report > 10:
                    progress(
                        stage,
                        "running" if workers else "waiting_for_qualified_workers",
                        len(pending),
                    )
                    last_report = time.monotonic()
                time.sleep(0.1 if workers else 1.0)
            summaries = []
            for repeat in range(cfg["repeats"]):
                payloads = [
                    records[key_for(stage, repeat, fold)]["payload"]
                    for fold in range(cfg["outer_folds"])
                ]
                summaries.append(module.repeat_summary(payloads, data, cfg))
            write_new(summary_path, summaries)
            ranges = []
            for weighting in ("window_equal", "person_equal"):
                for metric in summaries[0][weighting]:
                    values = [s[weighting][metric] for s in summaries]
                    ranges.append(
                        dict(
                            weighting=weighting,
                            metric=metric,
                            repeats=len(values),
                            median=float(np.median(values)),
                            minimum=min(values),
                            maximum=max(values),
                            role="split_and_training_sensitivity_not_confidence_interval",
                        )
                    )
            write_new(out / (stage + "_repeat_ranges.json"), ranges)
            progress(stage, "stage_completed")
        for name, expected in state["input_sha256"].items():
            if sha(ROOT / name) != expected:
                raise ValueError("Source mutated during CV")
        if not (out / "completion.json").exists():
            write_new(
                out / "completion.json",
                dict(
                    status="completed_20repeat_nested_person_CV",
                    completed_utc=datetime.now(timezone.utc).isoformat(),
                    folds=len(records),
                    real_primary_tests_executed=False,
                    outputs_sha256={
                        p.name: sha(p)
                        for p in out.iterdir()
                        if p.is_file() and p.name != "driver.lock"
                    },
                    not_completed=cfg["not_in_this_batch"],
                ),
            )
        progress("all", "completed_20repeat_nested_person_CV")
    except Exception as exc:
        progress("execution", "failed")
        write_new(out / ("error_" + uuid.uuid4().hex + ".json"), dict(error=repr(exc)))
        raise
    finally:
        client.close()
        lockfile.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/dask_prediction_repeats_20261003_v1.json",
    )
    p.add_argument("--resume", type=Path)
    p.add_argument("--scheduler", default="tcp://192.0.2.54:8786")
    args = p.parse_args()
    run(
        args.resume.resolve() if args.resume else prepare(args.config.resolve()),
        args.scheduler,
    )


if __name__ == "__main__":
    main()
