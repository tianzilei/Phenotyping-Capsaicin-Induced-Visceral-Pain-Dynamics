"""Execute native Python stability and training jobs until R environment is required."""

from __future__ import annotations
import argparse
import ast
import collections
import hashlib
import importlib
import json
import os
import subprocess
import sys
import time
import uuid
import zipfile
from datetime import datetime, timezone
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
from capsaicin.distributed_observation import tokens_to_arrays, summarize_column
from capsaicin.completion import fe_sufficient, solve_fe
from capsaicin.distributed_remaining import old_candidate_fit


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
        / f"dask_python_remaining_{stamp}_{uuid.uuid4().hex[:8]}"
    )
    for name in ("snapshot", "private_inputs", "results"):
        (out / name).mkdir(parents=True)
    tables = {}
    source_hashes = {}
    for key, item in cfg["sources"].items():
        source = ROOT / item["path"]
        manifest = ROOT / item["manifest"]
        m = json.loads(manifest.read_bytes())
        hashes = m.get("outputs_sha256", m.get("output_sha256", {}))
        expected = hashes[source.name]
        if sha(source) != expected:
            raise ValueError("Source output hash mismatch: " + key)
        source_hashes[item["path"]] = expected
        source_hashes[item["manifest"]] = sha(manifest)
        target = out / "private_inputs" / (key + ".csv")
        with target.open("xb") as f:
            f.write(source.read_bytes())
        tables[key] = pd.read_csv(
            target,
            dtype={"ID": str, "person_id": str, "subject_id": str},
            keep_default_na=False,
        )
    people = tables["people"].sort_values("ID").reset_index(drop=True)
    if len(people) != cfg["expected_people"] or people.ID.duplicated().any():
        raise ValueError("True-person support changed")
    values, _ = tokens_to_arrays(
        people[[f"VAS_{m}min" for m in range(1, 21)]].to_numpy()
    )
    cfg["prepared_input_sha256"] = {}
    cfg["cells"] = {s: [] for s in cfg["sequence"]}
    point_checks = []

    def save(key, data):
        path = out / "private_inputs" / (key + ".npz")
        with path.open("xb") as f:
            np.savez(f, **data)
        cfg["prepared_input_sha256"][key] = sha(path)

    for end in cfg["intervals"]:
        x = values[np.isfinite(values[:, :end]).all(axis=1), :end]
        if len(x) != cfg["expected_complete"][str(end)]:
            raise ValueError("Complete-person support changed")
        for transformation in cfg["transformations"]:
            key = f"V{end}_{transformation}"
            y = x if transformation == "raw" else x - x.mean(axis=1, keepdims=True)
            save(key, dict(x=y))
            for method in cfg["methods"]:
                for k in cfg["k"]:
                    cfg["cells"]["cluster"].append(
                        dict(
                            id=f"C{end}_{transformation}_{method}_k{k}",
                            data_key=key,
                            interval_key=str(end),
                            end=end,
                            transformation=transformation,
                            method=method,
                            k=k,
                        )
                    )
        for k in cfg["k"]:
            cfg["cells"]["recovery"].append(
                dict(
                    id=f"R{end}_k{k}",
                    data_key=f"V{end}_raw",
                    interval_key=str(end),
                    end=end,
                    k=k,
                )
            )
    # Only the pre-existing development pool participates in questionnaire/rest training.
    bcfg = cfg["baseline_recovery"]
    rest = tables["rest_development"]
    dev = rest[rest.pool.eq("development")].copy()
    for column in bcfg["rest_features"]:
        dev[column] = pd.to_numeric(dev[column], errors="coerce")
    dev = dev[np.isfinite(dev[bcfg["rest_features"]]).all(axis=1)]
    data = people.merge(dev, left_on="ID", right_on="subject_id", validate="one_to_one")
    cfg["baseline_development_people"] = len(data)
    bv, _ = tokens_to_arrays(data[[f"VAS_{m}min" for m in range(1, 21)]].to_numpy())
    for end in cfg["intervals"]:
        ok = np.isfinite(bv[:, :end]).all(axis=1)
        frame = data[ok]
        numeric = (
            frame[bcfg["numeric_questionnaire"] + bcfg["rest_features"]]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(float)
        )
        categorical = (
            frame[bcfg["categorical_questionnaire"]].astype(str).to_numpy(dtype=str)
        )
        key = f"B{end}"
        save(key, dict(x=bv[ok, :end], numeric=numeric, categorical=categorical))
        for k in cfg["k"]:
            cfg["cells"]["baseline"].append(
                dict(
                    id=f"B{end}_k{k}",
                    data_key=key,
                    interval_key=str(end),
                    end=end,
                    k=k,
                    n_people=len(frame),
                )
            )

    def add_candidate(kind, key, frame, outcome, predictors, expected_rows):
        d = frame.copy()
        if d.duplicated(["person_id", "block"]).any():
            raise ValueError("Duplicate candidate person/block")
        for column in [outcome, *predictors]:
            d[column] = pd.to_numeric(d[column], errors="raise")
        if not np.isfinite(d[[outcome, *predictors]]).all(axis=None):
            raise ValueError("Nonfinite frozen candidate input")
        counts = d.groupby("person_id").block.nunique()
        if (counts < 2).any():
            raise ValueError("Candidate has fewer than two actual blocks")
        p = fe_sufficient(d, outcome, predictors)
        if p is None:
            raise ValueError("Empty candidate source")
        cell = dict(
            id="A_" + digest([kind, *key])[:16],
            data_key="A_" + digest([kind, *key])[:16],
            kind=kind,
            p=len(predictors),
            labels=list(key),
            predictors=predictors,
            n_people=len(p["people"]),
            n_blocks=len(d),
        )
        prepared = dict(
            gram=p["gram"],
            row_counts=d.groupby("person_id", sort=True).size().to_numpy(int),
        )
        if kind == "joint22":
            base = fe_sufficient(d, outcome, predictors[:2])
            prepared["base_gram"] = base["gram"]
        fit = (
            old_candidate_fit(prepared, np.ones(len(p["people"])))
            if kind == "planned24"
            else solve_fe(p)
        )
        if fit is None:
            raise ValueError("Source point estimator unexpectedly inestimable")
        expected = np.asarray(expected_rows, float)
        if not np.allclose(fit["coefficients"], expected, rtol=1e-8, atol=1e-9):
            raise ValueError(
                "Current FE point differs from saved candidate coefficient"
            )
        point_checks.append(
            dict(
                cell=cell["id"],
                coefficients=fit["coefficients"].tolist(),
                expected=expected.tolist(),
                n_people=len(p["people"]),
                n_blocks=len(d),
            )
        )
        save(cell["data_key"], prepared)
        cfg["cells"]["candidate"].append(cell)

    for key, frame in tables["planned24_inputs"].groupby(["roi", "metric"], sort=True):
        row = tables["planned24_results"].set_index(["roi", "metric"]).loc[key]
        add_candidate(
            "planned24", key, frame, "value", ["vas_mean"], [row.candidate_beta]
        )
    for key, frame in tables["egg66_inputs"].groupby(
        ["roi", "metric", "predictor"], sort=True
    ):
        row = (
            tables["egg66_results"]
            .set_index(["roi", "metric", "egg_descriptor"])
            .loc[key]
        )
        add_candidate(
            "egg66",
            key,
            frame,
            "hb_within_person_SD",
            ["egg_value"],
            [row.candidate_beta],
        )
    for key, frame in tables["joint22_inputs"].groupby(["roi", "metric"], sort=True):
        rows = tables["joint22_results"].set_index(["roi", "metric", "predictor"])
        expected = [
            rows.loc[(*key, name), "candidate_beta"]
            for name in ["HR", "candidate_RR_RMSSD", "value"]
        ]
        add_candidate(
            "joint22",
            key,
            frame,
            "vas_mean",
            ["candidate_HR", "candidate_RR_RMSSD", "hb_within_person_SD"],
            expected,
        )
    for kind, n in cfg["candidate_targets"].items():
        if sum(c["kind"] == kind for c in cfg["cells"]["candidate"]) != n:
            raise ValueError("Candidate target roster changed")
    write_new(
        out / "candidate_point_verification.json",
        dict(
            status="PASS",
            targets=len(point_checks),
            coefficient_count=sum(len(x["coefficients"]) for x in point_checks),
            checks=point_checks,
        ),
    )
    sources = [
        config_path,
        Path(__file__),
        ROOT / "scripts/run_dask_derivative_development.py",
        ROOT / "scripts/run_reanalysis_clustering.py",
        ROOT / "scripts/complete_analysis_20261002.py",
        ROOT / "scripts/run_candidate_associations.py",
        ROOT / "src/capsaicin/distributed_remaining.py",
        ROOT / "src/capsaicin/distributed_cluster_legacy.py",
        ROOT / "src/capsaicin/completion.py",
        ROOT / "src/capsaicin/distributed_prediction.py",
        ROOT / "src/capsaicin/distributed_observation.py",
        ROOT / "src/capsaicin/distributed_development.py",
        ROOT / cfg["runtime_lock"],
        ROOT / cfg["parent"],
        ROOT / cfg["prior_scientific_config"],
    ]
    code_hashes = {}
    for source in sources:
        target = out / "snapshot" / source.name
        with target.open("xb") as f:
            f.write(source.read_bytes())
        code_hashes[source.name] = sha(target)
    original = (out / "snapshot/run_reanalysis_clustering.py").read_text()
    extracted = (out / "snapshot/distributed_cluster_legacy.py").read_text()
    for node in ast.parse(original).body:
        if isinstance(node, ast.FunctionDef) and node.name in ("dtw", "pam", "fuzzy"):
            if ast.get_source_segment(original, node) not in extracted:
                raise ValueError("Legacy clustering numerical kernel changed")
    package = "capsaicin_remaining_" + digest(code_hashes)[:16]
    bundle = out / (package + ".zip")
    with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(package + "/__init__.py", "")
        for name in [
            "distributed_remaining.py",
            "distributed_cluster_legacy.py",
            "completion.py",
            "distributed_prediction.py",
            "distributed_observation.py",
            "distributed_development.py",
        ]:
            z.write(out / "snapshot" / name, package + "/" + name)
    write_new(
        out / "run_manifest.json",
        dict(
            config=cfg,
            config_sha256=digest(cfg),
            input_sha256=source_hashes,
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
            created_utc=datetime.now(timezone.utc).isoformat(),
            scope="native_Python_exploratory_stability_until_remote_R_required",
        ),
    )
    print(
        json.dumps(
            dict(
                run_directory=str(out),
                cells={s: len(c) for s, c in cfg["cells"].items()},
                candidate_coefficients=len(point_checks),
            )
        ),
        flush=True,
    )
    return out


def jobs_for(cfg, stage):
    jobs = []
    for cell in cfg["cells"][stage]:
        if stage in ("cluster", "candidate"):
            count = (
                cfg["cluster_replicates"]
                if stage == "cluster"
                else cfg["candidate_replicates"]
            )
            batch = (
                cfg["cluster_batch_size"]
                if stage == "cluster"
                else cfg["candidate_batch_size"]
            )
            for start in range(0, count, batch):
                jobs.append(
                    dict(
                        id=f"{stage}__{cell['id']}__{start:05d}",
                        stage=stage,
                        cell=cell,
                        start=start,
                        stop=min(start + batch, count),
                    )
                )
        else:
            c = cfg["recovery"] if stage == "recovery" else cfg["baseline_recovery"]
            for repeat in range(c["repeats"]):
                for fold in range(c["folds"]):
                    jobs.append(
                        dict(
                            id=f"{stage}__{cell['id']}__r{repeat:03d}__f{fold}",
                            stage=stage,
                            cell=cell,
                            repeat=repeat,
                            fold=fold,
                        )
                    )
    return jobs


def mc_summary(values, cfg, family, bounds, absolute):
    c = dict(
        MC_total_error_probability=cfg["MC_error_per_stage"],
        statistic_family_size=family,
    )
    row = summarize_column(np.asarray(values, float), c, bounds, "native_units")
    mc = row.get("MC_max_endpoint_half_width")
    if row.get("valid", 0):
        width = row["empirical_range_width"]
        relative = mc is not None and (
            mc <= cfg["MC_relative_tolerance"] * width if width else mc == 0
        )
        row["status"] = (
            "MC_PRECISION_MET"
            if relative and (absolute is None or mc <= absolute)
            else "MC_PRECISION_INSUFFICIENT"
        )
    row["absolute_MC_tolerance"] = absolute
    return row


def summarize_stage(out, cfg, records, stage):
    summary = []
    repeat_rows = []
    for cell in cfg["cells"][stage]:
        payloads = [
            v["payload"]
            for v in records.values()
            if v["payload"]["stage"] == stage and v["payload"]["cell"] == cell["id"]
        ]
        if stage in ("cluster", "candidate"):
            payloads.sort(key=lambda p: p["job"]["start"])
            rows = np.asarray(
                sum((p["result"]["statistics"] for p in payloads), []), float
            )
            attempted = (
                cfg["cluster_replicates"]
                if stage == "cluster"
                else cfg["candidate_replicates"]
            )
            if len(rows) != attempted:
                raise ValueError("Missing logical bootstrap replicates")
            failures = sum(
                sum(f is not None for f in p["result"]["failures"]) for p in payloads
            )
            if stage == "cluster":
                specs = [
                    ("legacy_ARI", [-1, 1], cfg["MC_cluster_ARI_absolute"]),
                    ("OOB_ARI", [-1, 1], cfg["MC_cluster_ARI_absolute"]),
                    (
                        "legacy_matched_mean_Jaccard",
                        [0, 1],
                        cfg["MC_cluster_proportion_absolute"],
                    ),
                ]
                if cell["method"] == "fuzzy_cmeans":
                    specs += [
                        (
                            "entropy_all",
                            [0, float(np.log(cell["k"]))],
                            cfg["MC_cluster_entropy_absolute"],
                        ),
                        (
                            "entropy_OOB",
                            [0, float(np.log(cell["k"]))],
                            cfg["MC_cluster_entropy_absolute"],
                        ),
                    ]
                family = 176
                flags = sum((p["result"]["flags"] for p in payloads), [])
                extra = dict(
                    reference_cluster_sizes=payloads[0]["result"][
                        "reference_cluster_sizes"
                    ],
                    collapsed_fits=sum(f["collapsed_fit"] is True for f in flags),
                    minimum_OOB_people=min(f["oob_people"] for f in flags),
                    maximum_OOB_people=max(f["oob_people"] for f in flags),
                    constant_OOB_partitions=sum(
                        f["oob_reference_classes"] == 1 or f["oob_fitted_classes"] == 1
                        for f in flags
                    ),
                )
            else:
                specs = [
                    (
                        "coefficient_" + name,
                        [None, None],
                        cfg["MC_candidate_coefficient_absolute"],
                    )
                    for name in cell["predictors"]
                ]
                if cell["kind"] == "joint22":
                    specs.append(
                        (
                            "same_row_SSE_reduction",
                            [0, None],
                            cfg["MC_candidate_SSE_absolute"],
                        )
                    )
                family = cfg["candidate_statistics"]
                extra = dict(
                    primary_p=None,
                    primary_q=None,
                    eligible_people=cell["n_people"],
                    eligible_blocks=cell["n_blocks"],
                    interval_role="success_conditional_descriptive_stability_no_physiological_validation",
                )
            for j, (name, bounds, absolute) in enumerate(specs):
                row = mc_summary(rows[:, j], cfg, family, bounds, absolute)
                row.update(
                    cell=cell["id"],
                    cell_description=cell,
                    statistic=name,
                    failed_replicates=failures,
                    **extra,
                )
                if (
                    stage == "candidate"
                    and failures > cfg["candidate_failure_limit"] * attempted
                ):
                    row["interval_publication_status"] = (
                        "WITHHELD_EXCESS_ESTIMATOR_FAILURE"
                    )
                    row["descriptive_lower"] = None
                    row["descriptive_upper"] = None
                else:
                    row["interval_publication_status"] = "descriptive_range"
                    row["descriptive_lower"] = row.get("lower", {}).get("estimate")
                    row["descriptive_upper"] = row.get("upper", {}).get("estimate")
                summary.append(row)
        else:
            c = cfg["recovery"] if stage == "recovery" else cfg["baseline_recovery"]
            for repeat in range(c["repeats"]):
                parts = [p for p in payloads if p["job"]["repeat"] == repeat]
                if sorted(p["job"]["fold"] for p in parts) != list(range(c["folds"])):
                    raise ValueError("Missing training fold")
                estimated = [
                    p
                    for p in parts
                    if p["result"]["status"] == "estimated_training_partition_recovery"
                ]
                if estimated:
                    n = estimated[0]["result"]["n_people"]
                    seen = []
                    for p in estimated:
                        r = p["result"]
                        seen += r["test_rows"]
                        if set(r["train_rows"]) & set(r["test_rows"]):
                            raise ValueError("Subject leakage")
                    if len(estimated) == c["folds"] and sorted(seen) != list(range(n)):
                        raise ValueError("Subject OOF coverage incomplete")
                groups = collections.defaultdict(list)
                for p in estimated:
                    for metric in p["result"]["metrics"]:
                        groups[(metric["prefix"], metric["model"])].append(metric)
                for (prefix, model), metrics in groups.items():
                    a = np.asarray([m["values"] for m in metrics])
                    repeat_rows.append(
                        dict(
                            cell=cell["id"],
                            repeat=repeat,
                            prefix=prefix,
                            model=model,
                            attempted_folds=c["folds"],
                            estimated_folds=len(metrics),
                            inestimable_folds=c["folds"] - len(metrics),
                            repeat_complete=len(metrics) == c["folds"],
                            accuracy_equal_fold_mean=float(a[:, 0].mean()),
                            balanced_accuracy_equal_fold_mean=float(a[:, 1].mean()),
                            macro_F1_equal_fold_mean=float(a[:, 2].mean()),
                            status="all_folds_estimated"
                            if len(metrics) == c["folds"]
                            else "conditional_on_estimable_folds_not_complete_repeat",
                        )
                    )
            groups = collections.defaultdict(list)
            for row in repeat_rows:
                if row["cell"] == cell["id"]:
                    groups[(row["prefix"], row["model"])].append(row)
            for (prefix, model), rows in groups.items():
                for metric in [
                    "accuracy_equal_fold_mean",
                    "balanced_accuracy_equal_fold_mean",
                    "macro_F1_equal_fold_mean",
                ]:
                    valid = [r[metric] for r in rows if r["repeat_complete"]]
                    summary.append(
                        dict(
                            cell=cell["id"],
                            cell_description=cell,
                            prefix=prefix,
                            model=model,
                            metric=metric,
                            attempted_repeats=c["repeats"],
                            complete_repeats=len(valid),
                            incomplete_repeats=c["repeats"] - len(valid),
                            median=float(np.median(valid)) if valid else None,
                            minimum=min(valid) if valid else None,
                            maximum=max(valid) if valid else None,
                            scope="training_partition_recovery_split_sensitivity_not_population_CI",
                            missing_classes="macroF1_frozen_allk_zero_division0_balanced_accuracy_present_reference_classes",
                        )
                    )
            if not groups:
                summary.append(
                    dict(
                        cell=cell["id"],
                        cell_description=cell,
                        status="INESTIMABLE_ALL_REPEATS",
                        attempted_repeats=c["repeats"],
                        complete_repeats=0,
                        reason_counts=dict(
                            collections.Counter(
                                p["result"].get("reason") for p in payloads
                            )
                        ),
                    )
                )
    write_new(out / (stage + "_summary.json"), summary)
    if repeat_rows:
        write_new(out / (stage + "_repeat_metrics.json"), repeat_rows)
    return summary


def synthetic_checks(cfg):
    rng = np.random.default_rng(841)
    x = rng.uniform(0, 10, (36, 10))
    checks = []
    qcfg = dict(
        cfg,
        prepared_input_sha256=dict(cfg["prepared_input_sha256"], QA="synthetic_only"),
    )
    for method in ["euclidean_kmeans", "dtw_pam", "fuzzy_cmeans"]:
        cell = dict(
            id="QA_" + method,
            data_key="QA",
            interval_key="10",
            end=10,
            transformation="raw",
            method=method,
            k=2,
        )
        checks.append(
            (
                qcfg,
                dict(x=x),
                dict(id="QA_" + method, stage="cluster", cell=cell, start=0, stop=3),
            )
        )
    cell = dict(id="QA_recovery", data_key="QA", interval_key="10", end=10, k=2)
    checks.append(
        (
            qcfg,
            dict(x=x),
            dict(id="QA_recovery", stage="recovery", cell=cell, repeat=0, fold=0),
        )
    )
    b = cfg["baseline_recovery"]
    numeric = rng.normal(
        size=(36, len(b["numeric_questionnaire"]) + len(b["rest_features"]))
    )
    categories = np.where(
        rng.random((36, len(b["categorical_questionnaire"]))) < 0.5, "a", "b"
    )
    checks.append(
        (
            qcfg,
            dict(x=x, numeric=numeric, categorical=categories),
            dict(
                id="QA_baseline",
                stage="baseline",
                cell=dict(cell, id="QA_baseline"),
                repeat=0,
                fold=0,
            ),
        )
    )
    g = np.repeat(np.arange(16), 4)
    block = np.tile(np.arange(4), 16)
    z = rng.normal(size=64)
    y = 2 * z + g + 0.1 * block + rng.normal(0, 0.1, 64)
    p = fe_sufficient(
        pd.DataFrame(dict(person_id=g, block=block, x=z, y=y)), "y", ["x"]
    )
    checks.append(
        (
            qcfg,
            dict(gram=p["gram"], row_counts=np.full(16, 4)),
            dict(
                id="QA_candidate",
                stage="candidate",
                cell=dict(
                    id="QA_candidate",
                    data_key="QA",
                    kind="planned24",
                    p=1,
                    predictors=["x"],
                ),
                start=0,
                stop=3,
            ),
        )
    )
    return checks


def run(out, scheduler):
    state = json.loads((out / "run_manifest.json").read_bytes())
    cfg = state["config"]
    for name, h in state["code_sha256"].items():
        if sha(out / "snapshot" / name) != h:
            raise ValueError("Frozen code/config changed")
    for file in [Path(__file__), ROOT / "scripts/run_dask_derivative_development.py"]:
        if sha(file) != state["code_sha256"][file.name]:
            raise ValueError("Driver changed since freeze")
    bundle = out / state["bundle"]
    if sha(bundle) != state["bundle_sha256"]:
        raise ValueError("Worker bundle corrupted")
    inputs = {}
    for key, h in cfg["prepared_input_sha256"].items():
        path = out / "private_inputs" / (key + ".npz")
        if sha(path) != h:
            raise ValueError("Prepared input corrupted")
        with np.load(path, allow_pickle=False) as f:
            inputs[key] = {k: f[k] for k in f.files}
    jobs = {s: jobs_for(cfg, s) for s in cfg["sequence"]}
    alljobs = {job["id"]: job for group in jobs.values() for job in group}
    lockfile = out / "driver.lock"
    if lockfile.exists():
        p = json.loads(lockfile.read_bytes())
        if (
            psutil.pid_exists(p["pid"])
            and abs(psutil.Process(p["pid"]).create_time() - p["created"]) < 0.01
        ):
            raise ValueError("Another driver is active")
        lockfile.unlink()
    write_new(lockfile, dict(pid=os.getpid(), created=psutil.Process().create_time()))
    records = recover(out)

    def validate(task, item):
        p = item["payload"]
        if (
            task not in alljobs
            or p["task"] != task
            or p["job"] != alljobs[task]
            or p["config_sha256"] != state["config_sha256"]
            or p["input_sha256"]
            != cfg["prepared_input_sha256"][alljobs[task]["cell"]["data_key"]]
        ):
            raise ValueError("Checkpoint source/config/task mismatch")

    for task, item in records.items():
        validate(task, item)
    sys.path.insert(0, str(bundle))
    module = importlib.import_module(state["package"] + ".distributed_remaining")
    environment = importlib.import_module(
        state["package"] + ".distributed_development"
    ).environment
    lock = (out / "snapshot" / Path(cfg["runtime_lock"]).name).read_text()
    qas = synthetic_checks(cfg)
    reference_qa = [module.execute(c, d, j) for c, d, j in qas]
    client = Client(scheduler, set_as_default=False, timeout="30s")
    qualified = {}
    last_refresh = 0.0
    start = time.monotonic()
    seq = len(list(out.glob("progress_*.json")))

    def refresh():
        nonlocal last_refresh, qualified
        if time.monotonic() - last_refresh < 10:
            return
        workers = client.scheduler_info()["workers"]
        ports = reachable_workers(workers)
        new = sorted(
            a
            for a in set(workers) - set(qualified)
            if ports[a] and not a.startswith("tcp://192.0.2.54:")
        )
        if new:
            delivery = client.run(
                install_bundle,
                bundle.read_bytes(),
                sha(bundle),
                bundle.name,
                workers=new,
            )
            checks = client.run(environment, lock, workers=new)
            verified = {}
            # Every newly joined worker passes synthetic numerical QA before real work.
            for a, q in checks.items():
                if (
                    q["issues"]
                    or workers[a]["nthreads"] != 1
                    or workers[a]["memory_limit"] < 2 * 1024**3
                ):
                    continue
                for (c, d, j), expected in zip(qas, reference_qa):
                    f = client.submit(
                        module.execute,
                        c,
                        d,
                        j,
                        workers=[a],
                        allow_other_workers=False,
                        pure=False,
                        retries=0,
                    )
                    result = f.result(timeout=60)
                    compare_payloads(expected["payload"], result["payload"], 1e-8, 1e-9)
                    f.release()
                qualified[a] = q
                verified[a] = "six_synthetic_pipeline_checks_PASS"
            write_new(
                out / ("worker_environment_" + uuid.uuid4().hex + ".json"),
                dict(
                    delivery=delivery,
                    environment=checks,
                    numerical_QA=verified,
                    rtol=1e-8,
                    atol=1e-9,
                ),
            )
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
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            run_directory=str(out),
            completed_jobs=len(records),
            total_jobs=len(alljobs),
            stage_completed_jobs=sum(
                r["payload"]["stage"] == stage for r in records.values()
            ),
            stage_total_jobs=len(jobs.get(stage, [])),
            pending=pending,
            selected_workers=len(eligible()),
        )
        write_new(out / f"progress_{seq:06d}.json", value)
        print(json.dumps(value), flush=True)
        path = (
            Path.home()
            / ".local/share/capsaicin-dask/state/active-development-driver.json"
        )
        tmp = path.with_name("." + path.name + "." + str(os.getpid()))
        tmp.write_bytes(canonical(value) + b"\n")
        tmp.replace(path)

    try:
        receipt = client.run_on_scheduler(
            install_bundle, bundle.read_bytes(), sha(bundle), bundle.name
        )
        if not (out / "scheduler_bundle_delivery.json").exists():
            write_new(out / "scheduler_bundle_delivery.json", receipt)
        refresh()
        if not eligible():
            raise RuntimeError("No qualified remote workers")
        for stage in cfg["sequence"]:
            if (out / (stage + "_summary.json")).exists():
                continue
            tasks = [j for j in jobs[stage] if j["id"] not in records]
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
                    job = tasks[index]
                    index += 1
                    f = client.submit(
                        module.execute,
                        cfg,
                        inputs[job["cell"]["data_key"]],
                        job,
                        workers=workers,
                        allow_other_workers=False,
                        pure=False,
                        retries=0,
                    )
                    pending[f] = job["id"]
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
                if time.monotonic() - last_report > 15:
                    progress(
                        stage,
                        "running" if workers else "waiting_for_qualified_workers",
                        len(pending),
                    )
                    last_report = time.monotonic()
                time.sleep(0.1 if workers else 1.0)
            summarize_stage(out, cfg, records, stage)
            progress(stage, "stage_completed")
        for name, h in state["input_sha256"].items():
            if sha(ROOT / name) != h:
                raise ValueError("Source changed during execution")
        if not (out / "completion.json").exists():
            write_new(
                out / "completion.json",
                dict(
                    status="completed_native_Python_batch_remote_R_required_next",
                    completed_utc=datetime.now(timezone.utc).isoformat(),
                    jobs=len(records),
                    real_primary_tests_executed=False,
                    sealed_people_used=0,
                    outputs_sha256={
                        p.name: sha(p)
                        for p in out.iterdir()
                        if p.is_file() and p.name != "driver.lock"
                    },
                    remaining=cfg["not_in_this_batch"],
                ),
            )
        progress("all", "completed_native_Python_batch_remote_R_required_next")
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
        default=ROOT / "config/dask_python_remaining_20261003_v1.json",
    )
    p.add_argument("--resume", type=Path)
    p.add_argument("--scheduler", default="tcp://192.0.2.54:8786")
    a = p.parse_args()
    run(a.resume.resolve() if a.resume else prepare(a.config.resolve()), a.scheduler)


if __name__ == "__main__":
    main()
