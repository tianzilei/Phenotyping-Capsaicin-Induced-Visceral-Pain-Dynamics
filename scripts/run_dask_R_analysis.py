"""Standalone numerical helpers; legacy private-run orchestration is excluded."""

from __future__ import annotations
import collections
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from capsaicin.distributed_observation import summarize_column
from run_dask_derivative_development import write_new

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]


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
        if req.marker and (not req.marker.evaluate()):
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
        and (w["memory_limit"] >= config["runtime"]["worker_memory_minimum"])
    ]

    def probe(a):
        h, p = a.removeprefix("tcp://").rsplit(":", 1)
        try:
            with socket.create_connection((h, int(p)), timeout=1):
                pass
            return (a, True)
        except OSError:
            return (a, False)

    with ThreadPoolExecutor(max_workers=16) as pool:
        ports = dict(pool.map(probe, targets))
    ready = sorted((a for a in targets if ports[a]))[
        : config["runtime"]["host_concurrency"]
    ]
    return dict(
        status="transport_ready_R_QA_required" if ready else "BLOCKED_REMOTE_DATA_PORT",
        registered_host_workers=targets,
        ports=ports,
        selected_workers=ready,
        scheduler_only=not any(
            (a.startswith("tcp://192.0.2.54:") for a in info["workers"])
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
                if any((p["result"]["status"] != "estimated" for p in folds)):
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
                (
                    r.get("reason", "unknown")
                    for r in replicates
                    if r["status"] != "estimated"
                )
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
                    and (half <= absolute)
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
