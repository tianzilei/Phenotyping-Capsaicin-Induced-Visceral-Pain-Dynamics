"""Sequential distributed VAS and paired fixed-OOF descriptive resampling."""

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


def prediction_input(frame, people, stage, models):
    """Require identical target rows, folds, and people for paired model losses."""
    key = ["person_id", "time_min"] if stage == "next_rating" else ["person_id"]
    if set(frame.model) != set(models):
        raise ValueError("Model support differs from frozen model set")
    parts = [
        frame.loc[frame.model == name].set_index(key).sort_index() for name in models
    ]
    for p in parts:
        if p.index.duplicated().any():
            raise ValueError("Duplicate OOF person/target row")
    base = parts[0]
    for other in parts[1:]:
        if not base.index.equals(other.index):
            raise ValueError("Paired model target rows differ")
        if not np.array_equal(base.observed, other.observed) or not np.array_equal(
            base.fold, other.fold
        ):
            raise ValueError("Paired OOF targets or folds differ")
    ids = (
        base.index.get_level_values("person_id")
        if stage == "next_rating"
        else base.index
    )
    unique = sorted(set(ids))
    person_index = {sid: i for i, sid in enumerate(unique)}
    counts = np.zeros(len(unique), dtype=int)
    absolute = np.zeros((len(unique), len(models)))
    squared = np.zeros_like(absolute)
    folds = {}
    for j, sid in enumerate(ids):
        if sid not in people.index:
            raise ValueError("Prediction person absent from frozen cohort")
        values = people.loc[sid]
        if stage == "next_rating":
            minute = int(base.index[j][1])
            needed = [minute - 2, minute - 1, minute, minute + 1]
            if not all(pd.notna(values[f"VAS_{m}min"]) for m in needed):
                raise ValueError("OOF target bridges a missing minute")
            target = values[f"VAS_{minute + 1}min"]
            baseline = values[f"VAS_{minute}min"]
            if float(base.iloc[j].current) != baseline:
                raise ValueError("OOF current score mismatch")
        else:
            if not all(pd.notna(values[f"VAS_{m}min"]) for m in [1, 2, 3, 4, 5, 10]):
                raise ValueError("Incomplete five-to-ten eligible source")
            target, baseline = values.VAS_10min, values.VAS_5min
        if (
            float(base.iloc[j].observed) != target
            or float(base.iloc[j].predicted) != baseline
        ):
            raise ValueError("OOF source target/baseline differs from current scoring")
        fold = int(base.iloc[j].fold)
        if sid in folds and folds[sid] != fold:
            raise ValueError("One person's OOF rows span test folds")
        folds[sid] = fold
        i = person_index[sid]
        counts[i] += 1
        for k, p in enumerate(parts):
            predicted = float(p.iloc[j].predicted)
            if not np.isfinite(predicted):
                raise ValueError("Nonfinite OOF prediction")
            error = predicted - target
            absolute[i, k] += abs(error)
            squared[i, k] += error * error
    return (counts, absolute, squared), len(base)


def prepare(config_path):
    cfg = json.loads(config_path.read_bytes())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (
        Path.home()
        / ".local/share/capsaicin-dask/runs"
        / f"dask_observation_bootstrap_{stamp}_{uuid.uuid4().hex[:8]}"
    )
    (out / "results").mkdir(parents=True)
    (out / "snapshot").mkdir()
    (out / "private_inputs").mkdir()
    hashes = {}
    for key in ("people", "next_rating", "five_to_ten"):
        source = ROOT / cfg["sources"][key]
        manifest_path = ROOT / cfg["sources"][key + "_manifest"]
        expected = json.loads(manifest_path.read_bytes())["outputs_sha256"][source.name]
        if sha(source) != expected:
            raise ValueError("Frozen source output hash mismatch: " + key)
        hashes[cfg["sources"][key]] = expected
        hashes[cfg["sources"][key + "_manifest"]] = sha(manifest_path)
        target = out / "private_inputs" / (key + "_source.csv")
        with target.open("xb") as f:
            f.write(source.read_bytes())
    people = pd.read_csv(
        out / "private_inputs/people_source.csv", dtype=str, keep_default_na=False
    )
    if (
        len(people) != cfg["expected_support"]["VAS_observation"]
        or people.ID.duplicated().any()
    ):
        raise ValueError("Cohort person support changed")
    columns = [f"VAS_{m}min" for m in range(1, 21)]
    values, events = tokens_to_arrays(people[columns].to_numpy())
    numeric_people = pd.DataFrame(values, columns=columns, index=people.ID)
    prepared = {"VAS_observation": (values, events)}
    for stage in ("next_rating", "five_to_ten"):
        frame = pd.read_csv(
            out / "private_inputs" / (stage + "_source.csv"), dtype={"person_id": str}
        )
        item, windows = prediction_input(
            frame, numeric_people, stage, cfg["prediction"]["models"]
        )
        if len(item[0]) != cfg["expected_support"][stage]:
            raise ValueError("Prediction person support changed")
        if (
            stage == "next_rating"
            and windows != cfg["expected_support"]["next_rating_windows"]
        ):
            raise ValueError("Prediction target window support changed")
        prepared[stage] = item
    cfg["prepared_input_sha256"] = {}
    for stage, arrays in prepared.items():
        file = out / "private_inputs" / (stage + ".npz")
        with file.open("xb") as f:
            np.savez(f, **{f"a{i}": a for i, a in enumerate(arrays)})
        cfg["prepared_input_sha256"][stage] = sha(file)
    sources = [
        config_path,
        Path(__file__),
        ROOT / "scripts/run_dask_derivative_development.py",
        ROOT / "src/capsaicin/distributed_observation.py",
        ROOT / "src/capsaicin/distributed_development.py",
        ROOT / cfg["runtime_lock"],
        ROOT / cfg["parent"],
    ]
    code_hashes = {}
    for source in sources:
        destination = out / "snapshot" / source.name
        with destination.open("xb") as f:
            f.write(source.read_bytes())
        code_hashes[source.name] = sha(destination)
    package = "capsaicin_observation_" + digest(code_hashes)[:16]
    bundle = out / (package + ".zip")
    with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(package + "/__init__.py", "")
        for name in ("distributed_observation.py", "distributed_development.py"):
            z.write(out / "snapshot" / name, package + "/" + name)
    state = dict(
        created_utc=datetime.now(timezone.utc).isoformat(),
        config=cfg,
        config_sha256=digest(cfg),
        input_sha256=hashes,
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
        scope="descriptive_observation_and_fixed_OOF_no_new_scientific_tests",
    )
    write_new(out / "run_manifest.json", state)
    print(
        json.dumps({"run_directory": str(out), "sequence": cfg["sequence"]}), flush=True
    )
    return out


def statistic_specs(stage):
    if stage == "VAS_observation":
        return [
            (f"{name}_minute{minute}", bounds, unit)
            for name, bounds, unit in [
                ("mean_observed", [0, 10], "VAS"),
                ("fraction_observed", [0, 1], "proportion"),
                ("cumulative_E_marker", [0, 1], "proportion"),
                ("cumulative_T_marker", [0, 1], "proportion"),
            ]
            for minute in range(1, 21)
        ]
    models = ["last_value", "ridge", "random_forest"]
    specs = [
        (metric + "_" + model, [0, None], "VAS")
        for metric in ("MAE", "RMSE")
        for model in models
    ]
    specs += [
        (metric + "_" + model + "_minus_last_value", [None, None], "VAS")
        for metric in ("MAE", "RMSE")
        for model in models[1:]
    ]
    if stage == "next_rating":
        return [("window_equal_" + n, b, u) for n, b, u in specs] + [
            ("person_equal_" + n, b, u) for n, b, u in specs
        ]
    return specs


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
    if (
        sum(len(statistic_specs(s)) for s in cfg["sequence"])
        != cfg["statistic_family_size"]
    ):
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
    module = importlib.import_module(state["package"] + ".distributed_observation")
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
        new = sorted(set(info) - set(qualified))
        if new:
            client.upload_file(str(bundle))
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
        qualified = {a: q for a, q in qualified.items() if a in info}
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
            replicates_per_stage=cfg["replicates"],
        )
        write_new(out / f"progress_{seq:06d}.json", value)
        print(json.dumps(value), flush=True)

    try:
        refresh()
        if not qualified:
            raise RuntimeError("No qualified remote workers")
        for stage in cfg["sequence"]:
            if (out / (stage + "_summary.json")).exists():
                continue
            data = inputs[stage]
            engineering = out / (stage + "_engineering.json")
            if not engineering.exists():
                worker = eligible()[0]
                one = client.submit(
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
                ).result(timeout=60)
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
                    if item["payload"]["config_sha256"] != state["config_sha256"]:
                        raise ValueError("Wrong result configuration")
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
            for j, (name, bounds, unit) in enumerate(statistic_specs(stage)):
                row = summarize_column(values[:, j], cfg, bounds, unit)
                row.update(statistic=name, unit=unit, point=selected[0]["point"][j])
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
        default=ROOT / "config/dask_observation_bootstrap_20261003_v1.json",
    )
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--scheduler", default="tcp://192.0.2.54:8786")
    args = parser.parse_args()
    out = args.resume.resolve() if args.resume else prepare(args.config.resolve())
    run(out, args.scheduler)


if __name__ == "__main__":
    main()
