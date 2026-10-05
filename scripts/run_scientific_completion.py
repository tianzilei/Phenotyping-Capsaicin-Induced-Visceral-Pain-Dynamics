"""Freeze and execute the remaining observed-data analyses on remote workers."""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
import zipfile
import numpy as np
import pandas as pd
from distributed import Client

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from capsaicin.science_completion import canonical, finite_design, evaluate
from capsaicin.distributed_observation import tokens_to_arrays, summarize_column
from run_dask_derivative_development import sha, write_new
from run_dask_R_analysis import install, python_environment
from diagnose_dask_R_precision import portable


def matched(ss, rr, rule):
    required_all = rule.get("required_all", [])
    required_any = rule.get("required_any", [])
    regions = rule.get("required_region_any", [])
    if (
        not set(required_all) <= ss
        or (required_any and not set(required_any) & ss)
        or (regions and not set(regions) & rr)
    ):
        return False
    return bool(
        set(required_all) & ss
        or set(required_any) & ss
        or set(regions) & rr
        or set(rule.get("supportive", [])) & ss
        or set(rule.get("supportive_region_any", [])) & rr
    )


def prepare(config_path):
    config = json.loads(config_path.read_bytes())
    source = ROOT / config["source"]
    sm = ROOT / config["source_manifest"]
    source_manifest = json.loads(sm.read_bytes())
    if sha(source) != source_manifest["outputs_sha256"][source.name]:
        raise ValueError("Source changed")
    people = (
        pd.read_csv(source, dtype=str, keep_default_na=False)
        .sort_values("ID")
        .reset_index(drop=True)
    )
    if len(people) != config["expected_people"] or people.ID.duplicated().any():
        raise ValueError("Person frame changed")
    values, tokens = tokens_to_arrays(
        people[[f"VAS_{t}min" for t in range(1, 21)]].to_numpy()
    )
    if np.isfinite(values).sum() != config["expected_numeric_ratings"]:
        raise ValueError("Observation support changed")
    reference = ROOT / config["symptom_reference"]
    rm = json.loads((reference / "manifest.json").read_bytes())
    for name, h in rm["outputs_sha256"].items():
        if sha(reference / name) != h:
            raise ValueError("Symptom reference changed: " + name)
    constants = json.loads((reference / "constants.json").read_bytes())
    tree = ast.parse((reference / "rome_rules.py").read_text())
    rules = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "ROME_RULES" for t in n.targets)
    )
    sym = constants["symptom_code_map"]
    reg = constants["region_code_map"]
    sets = []
    known_s = []
    known_r = []
    for _, row in people.iterrows():
        s = re.sub(r"[;,|/\s]+", "", row.Symptom_codes)
        r = re.sub(r"\.0+$", "", row.Region_code)
        ss = set(s)
        rr = set(constants["composite_region_codes"].get(r, list(r)))
        if ss - set(sym) or rr - set(reg):
            raise ValueError("Unknown symptom/region code; no silent removal")
        sets.append((ss, rr))
        known_s.append(bool(s))
        known_r.append(bool(r))
    known_s = np.asarray(known_s, int)
    known_r = np.asarray(known_r, int)
    paired = known_s * known_r
    numerators = []
    denominators = []
    meta = []

    def add(indicator, denominator, row):
        numerators.append(np.asarray(indicator, int) * denominator)
        denominators.append(denominator)
        meta.append(
            dict(
                row,
                unit="proportion",
                absolute_MC_target=0.002,
                bounds=[0, 1],
                denominator_people=int(denominator.sum()),
            )
        )

    for code, label in sym.items():
        add(
            [code in s for s, r in sets],
            known_s,
            dict(kind="symptom", code=code, label=label),
        )
    for code, label in reg.items():
        add(
            [code in r for s, r in sets],
            known_r,
            dict(kind="region", code=code, label=label),
        )
    for s, sl in sym.items():
        for r, rl in reg.items():
            add(
                [s in ss and r in rr for ss, rr in sets],
                paired,
                dict(
                    kind="symptom_region_pair", code=s + "_" + r, label=sl + " / " + rl
                ),
            )
    for label, rule in rules.items():
        indicator = [
            matched({sym[s] for s in ss}, {reg[r] for r in rr}, rule) for ss, rr in sets
        ]
        add(
            indicator,
            paired,
            dict(
                kind="legacy_rule_pattern",
                code=label,
                label=label + " [rule alignment only]",
            ),
        )
    numerator = np.asarray(numerators)
    denominator = np.asarray(denominators)
    # The new complete grid must reproduce all previously reported nonzero counts.
    previous = pd.read_csv(reference / "marginal_counts.csv", dtype={"code": str})
    for _, r in previous.iterrows():
        index = next(
            i
            for i, m in enumerate(meta)
            if m["kind"] == r["kind"] and m["code"] == r["code"]
        )
        if numerator[index].sum() != r["count"]:
            raise ValueError("Marginal code count differs from reviewed reference")
    previous = pd.read_csv(reference / "rome_alignment_counts.csv")
    for _, r in previous.iterrows():
        index = next(
            i
            for i, m in enumerate(meta)
            if m["kind"] == "legacy_rule_pattern" and m["code"] == r["pattern"]
        )
        if numerator[index].sum() != r["count"]:
            raise ValueError("Rule matching differs from reviewed reference")
    supports, changes, intervals = finite_design(
        values, tuple(config["finite_changes"]["h_minutes"])
    )
    fm = []
    for interval in intervals:
        for statistic in config["finite_changes"]["statistics"]:
            proportion = statistic.endswith("proportion")
            rate = statistic.endswith("rate")
            h = interval["h_minutes"]
            fm.append(
                dict(
                    interval,
                    statistic=statistic,
                    unit="proportion"
                    if proportion
                    else "VAS/minute"
                    if rate
                    else "VAS",
                    absolute_MC_target=0.002 if proportion else 0.01,
                    bounds=[0, 1]
                    if proportion
                    else [-10 / h, 10 / h]
                    if rate
                    else [-10, 10],
                )
            )
    prepared = dict(
        symptoms=dict(numerator=numerator, denominator=denominator),
        finite_changes=dict(
            support=supports,
            change=changes,
            h=np.array([m["h_minutes"] for m in intervals]),
        ),
    )
    metadata = dict(symptoms=meta, finite_changes=fm)
    out = (
        Path.home()
        / ".local/share/capsaicin-dask/runs"
        / (
            "science_completion_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    for directory in ["snapshot", "private_inputs", "results"]:
        (out / directory).mkdir(parents=True)
    (out / "private_inputs/people_source.csv").write_bytes(source.read_bytes())
    files = [
        str(config_path.relative_to(ROOT)),
        "src/capsaicin/science_completion.py",
        "src/capsaicin/distributed_observation.py",
        "scripts/run_scientific_completion.py",
        "scripts/diagnose_dask_R_precision.py",
        "scripts/run_dask_R_analysis.py",
        config["runtime_lock"],
    ]
    snapshots = {}
    for name in files:
        p = out / "snapshot" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((ROOT / name).read_bytes())
        snapshots[name] = sha(p)
    for name in ["constants.json", "rome_rules.py", "rome_matcher.py"]:
        p = out / "snapshot" / name
        p.write_bytes((reference / name).read_bytes())
        snapshots[name] = sha(p)
    input_hashes = {
        config["source"]: sha(source),
        config["source_manifest"]: sha(sm),
        str(reference / "manifest.json"): sha(reference / "manifest.json"),
    }
    prepared_hashes = {}
    for stage, data in prepared.items():
        p = out / "private_inputs" / (stage + ".npz")
        with p.open("xb") as f:
            np.savez(f, **data)
        prepared_hashes[stage] = sha(p)
    package = (
        "capsaicin_science_" + snapshots["src/capsaicin/science_completion.py"][:16]
    )
    bundle = out / (package + ".zip")
    with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in [
            (package + "/__init__.py", b""),
            (
                package + "/science_completion.py",
                (ROOT / "src/capsaicin/science_completion.py").read_bytes(),
            ),
        ]:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, data)
    manifest = dict(
        config=config,
        config_sha256=hashlib.sha256(canonical(config)).hexdigest(),
        input_sha256=input_hashes,
        prepared_sha256=prepared_hashes,
        snapshot_sha256=snapshots,
        metadata=metadata,
        package=package,
        bundle=bundle.name,
        bundle_sha256=sha(bundle),
        expected_jobs=len(config["sequence"])
        * int(np.ceil(config["replicates_per_stage"] / config["batch_size"])),
        created_utc=datetime.now(timezone.utc).isoformat(),
        git_revision=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        dirty_diff_sha256=hashlib.sha256(
            subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT)
        ).hexdigest(),
        python=sys.version,
        primary_p_q=None,
        sealed_people_used=0,
    )
    write_new(out / "manifest.json", manifest)
    # Descriptive point statistics use the same frozen targets as the bootstrap.
    for stage, data in prepared.items():
        point = evaluate(stage, data, np.ones((1, len(people)), int))[0]
        rows = [
            dict(
                m,
                point=float(v) if np.isfinite(v) else None,
                count=int(numerator[i].sum()) if stage == "symptoms" else None,
            )
            for i, (m, v) in enumerate(zip(metadata[stage], point))
        ]
        write_new(out / (stage + "_point.json"), rows)
    write_new(
        out / "supports.json",
        dict(
            people=len(people),
            numeric_ratings=int(np.isfinite(values).sum()),
            symptom_recorded=int(known_s.sum()),
            region_recorded=int(known_r.sum()),
            both_recorded=int(paired.sum()),
            symptom_unrecorded=int((1 - known_s).sum()),
            region_unrecorded=int((1 - known_r).sum()),
            finite_intervals=intervals,
        ),
    )
    print(
        json.dumps(
            dict(
                run_directory=str(out),
                jobs=manifest["expected_jobs"],
                families={s: len(metadata[s]) for s in metadata},
            )
        ),
        flush=True,
    )
    return out


def run(out, scheduler):
    m = json.loads((out / "manifest.json").read_bytes())
    cfg = m["config"]
    for name, h in m["snapshot_sha256"].items():
        if sha(out / "snapshot" / name) != h:
            raise ValueError("Frozen source changed")
    for name, h in m["input_sha256"].items():
        if sha(ROOT / name) != h:
            raise ValueError("Original input changed")
    for name in [
        "scripts/run_scientific_completion.py",
        "src/capsaicin/science_completion.py",
        "src/capsaicin/distributed_observation.py",
    ]:
        if sha(ROOT / name) != m["snapshot_sha256"][name]:
            raise ValueError("Active code differs from frozen source")
    bundle = out / m["bundle"]
    if sha(bundle) != m["bundle_sha256"]:
        raise ValueError("Worker bundle changed")
    prepared = {}
    for stage, h in m["prepared_sha256"].items():
        p = out / "private_inputs" / (stage + ".npz")
        if sha(p) != h:
            raise ValueError("Prepared input changed")
        with np.load(p, allow_pickle=False) as f:
            prepared[stage] = {key: f[key] for key in f.files}
    journal = out / "checkpoint_journal.jsonl"
    records = {}
    if journal.exists():
        for line in journal.read_bytes().splitlines(keepends=True):
            if not line.endswith(b"\n"):
                raise ValueError("Incomplete journal retained for explicit repair")
            entry = json.loads(line)
            p = out / "results" / (entry["task"] + ".npz")
            if entry["task"] in records or sha(p) != entry["file_sha256"]:
                raise ValueError("Checkpoint corruption or duplicate")
            records[entry["task"]] = entry
    lock = out / "driver.lock"
    if lock.exists():
        raise RuntimeError("Driver lock exists; no concurrent run allowed")
    write_new(lock, dict(pid=os.getpid()))
    try:
        sys.path.insert(0, str(bundle))
        module = importlib.import_module(m["package"] + ".science_completion")
        with Client(scheduler, set_as_default=False) as client:
            info = client.scheduler_info()
            workers = []
            for host, maximum in [("192.0.2.186", 8), ("192.0.2.57", 4)]:
                candidates = sorted(
                    a
                    for a, w in info["workers"].items()
                    if a.startswith("tcp://" + host + ":")
                    and w["nthreads"] == 1
                    and w["memory_limit"] >= 2 * 1024**3
                )
                workers += candidates[:maximum]
            if not workers or any(client.processing(workers=workers).values()):
                raise RuntimeError("No idle qualified remote compute workers")
            issues = client.run(
                portable(python_environment),
                (ROOT / cfg["runtime_lock"]).read_text(),
                workers=list(info["workers"]),
            )
            if any(issues.values()):
                raise ValueError("Python worker lock mismatch")
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
                out / ("worker_environment_" + uuid.uuid4().hex + ".json"),
                dict(
                    workers=workers, Python_lock_issues=issues, local_compute_workers=0
                ),
            )
            for stage in cfg["sequence"]:
                summary = out / (stage + "_summary.json")
                if summary.exists():
                    continue
                batches = [
                    (start, min(start + cfg["batch_size"], cfg["replicates_per_stage"]))
                    for start in range(
                        0, cfg["replicates_per_stage"], cfg["batch_size"]
                    )
                ]
                pending = {}
                index = 0
                last = 0
                while index < len(batches) or pending:
                    while index < len(batches) and len(pending) < len(workers):
                        start, stop = batches[index]
                        index += 1
                        task = f"{stage}__{start:06d}"
                        if task in records:
                            continue
                        f = client.submit(
                            module.execute_batch,
                            cfg,
                            prepared[stage],
                            stage,
                            start,
                            stop,
                            workers=workers,
                            allow_other_workers=False,
                            pure=False,
                            retries=0,
                        )
                        pending[f] = (task, start, stop)
                    for f in [f for f in pending if f.done()]:
                        task, start, stop = pending.pop(f)
                        r = f.result()
                        f.release()
                        if (r["stage"], r["start"], r["stop"]) != (stage, start, stop):
                            raise ValueError("Task identity mismatch")
                        path = out / "results" / (task + ".npz")
                        with path.open("xb") as handle:
                            handle.write(r.pop("blob"))
                            handle.flush()
                            os.fsync(handle.fileno())
                        entry = dict(
                            task=task,
                            file_sha256=sha(path),
                            config_sha256=m["config_sha256"],
                            input_sha256=m["prepared_sha256"][stage],
                            **r,
                        )
                        with journal.open("ab") as handle:
                            handle.write(canonical(entry) + b"\n")
                            handle.flush()
                            os.fsync(handle.fileno())
                        records[task] = entry
                    if time.monotonic() - last > 15:
                        print(
                            json.dumps(
                                dict(
                                    stage=stage,
                                    completed=len(records),
                                    total=m["expected_jobs"],
                                    pending=len(pending),
                                )
                            ),
                            flush=True,
                        )
                        last = time.monotonic()
                    time.sleep(0.05)
                arrays = []
                for start, stop in batches:
                    r = records[f"{stage}__{start:06d}"]
                    with np.load(
                        out / "results" / (r["task"] + ".npz"), allow_pickle=False
                    ) as f:
                        values = f["values"]
                    if (
                        list(values.shape) != r["values_shape"]
                        or hashlib.sha256(values.astype("<f8").tobytes()).hexdigest()
                        != r["logical_values_sha256"]
                    ):
                        raise ValueError("Logical values changed")
                    arrays.append(values)
                values = np.concatenate(arrays)
                del arrays
                point = json.loads((out / (stage + "_point.json")).read_bytes())
                summaries = []
                for i, (metadata, p) in enumerate(zip(m["metadata"][stage], point)):
                    column = values[:, i]
                    valid = column[np.isfinite(column)]
                    result = summarize_column(
                        valid,
                        dict(
                            MC_total_error_probability=cfg["MC"]["error_per_stage"],
                            statistic_family_size=values.shape[1],
                        ),
                        metadata["bounds"],
                        metadata["unit"],
                    )
                    half = result.get("MC_max_endpoint_half_width")
                    width = result.get("empirical_range_width")
                    met = (
                        half is not None
                        and width is not None
                        and half <= metadata["absolute_MC_target"]
                        and half <= cfg["MC"]["relative_tolerance"] * width
                    )
                    result.update(
                        metadata,
                        point=p["point"],
                        attempted=len(column),
                        valid=len(valid),
                        undefined=int((~np.isfinite(column)).sum()),
                        status="MC_PRECISION_MET"
                        if met
                        else "MC_PRECISION_INSUFFICIENT",
                        uncertainty_role="success_conditional_descriptive_resampling_range_not_population_CI",
                    )
                    summaries.append(result)
                write_new(summary, summaries)
                del values
        for name, h in m["input_sha256"].items():
            if sha(ROOT / name) != h:
                raise ValueError("Source changed during run")
        if len(records) != m["expected_jobs"]:
            raise ValueError("Incomplete queue")
        if not (out / "completion.json").exists():
            write_new(
                out / "completion.json",
                dict(
                    status="completed_observed_support_exploratory_analyses",
                    jobs=len(records),
                    outputs_sha256={
                        p.name: sha(p)
                        for p in out.iterdir()
                        if p.is_file() and p.name != "driver.lock"
                    },
                    primary_p_q=None,
                    sealed_people_used=0,
                ),
            )
        print(
            json.dumps(
                dict(
                    run_directory=str(out),
                    jobs=len(records),
                    status="completed_observed_support_exploratory_analyses",
                )
            ),
            flush=True,
        )
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/scientific_completion_20261004_v1.json",
    )
    p.add_argument("--run", type=Path)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--scheduler", default="tcp://192.0.2.54:8786")
    a = p.parse_args()
    out = a.run.resolve() if a.run else prepare(a.config.resolve())
    if a.execute:
        run(out, a.scheduler)
