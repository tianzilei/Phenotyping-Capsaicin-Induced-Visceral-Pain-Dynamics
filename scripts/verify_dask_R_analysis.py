"""Read-only verification of frozen R checkpoints; never start new R fits.

Audit outputs must be outside Git. A partial audit reports progress only.
MC ranks are enumerated independently of the driver's binary-search reducer.
"""

from __future__ import annotations

import argparse
import collections
from datetime import datetime, timezone
from functools import lru_cache
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import binom

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from capsaicin.distributed_r import canonical, sha_bytes
from capsaicin.distributed_r_plan import jobs, long_rows, request_for
from capsaicin.distributed_observation import tokens_to_arrays
from run_dask_derivative_development import recover, sha, write_new


@lru_cache(maxsize=None)
def enumerated_ranks(n, probability, gamma):
    """Include sentinel ranks; directly enumerate both binomial inequalities."""
    if n < 1 or not 0 < probability < 1 or not 0 < gamma < 1:
        raise ValueError("Invalid MC rank parameters")
    lower = np.arange(n + 1)
    upper = np.arange(1, n + 2)
    r = int(lower[binom.cdf(lower - 1, n, probability) <= gamma / 2][-1])
    s = int(upper[binom.sf(upper - 1, n, probability) <= gamma / 2][0])
    return r, s


def independently_summarize(values, gamma, bounds):
    ordered = np.sort(np.asarray(values, float))
    if not len(ordered) or not np.isfinite(ordered).all():
        raise ValueError("Expected finite successful replicate statistics")
    result = {}
    for label, probability in [("lower", 0.025), ("upper", 0.975)]:
        r, s = enumerated_ranks(len(ordered), probability, gamma)
        estimate = float(ordered[math.ceil(len(ordered) * probability) - 1])
        low = float(ordered[r - 1]) if r else bounds[0]
        high = float(ordered[s - 1]) if s <= len(ordered) else bounds[1]
        half = (
            None
            if low is None or high is None
            else max(estimate - low, high - estimate)
        )
        result[label] = dict(
            estimate=estimate,
            lower_MC=low,
            upper_MC=high,
            lower_rank=r,
            upper_rank=s,
            MC_half_width=half,
        )
    result["empirical_range_width"] = (
        result["upper"]["estimate"] - result["lower"]["estimate"]
    )
    halves = [result[k]["MC_half_width"] for k in ["lower", "upper"]]
    result["MC_max_endpoint_half_width"] = max(halves) if None not in halves else None
    return result


def numeric_equal(actual, expected, label, rtol=1e-12, atol=1e-12):
    if isinstance(expected, dict):
        for key, value in expected.items():
            numeric_equal(actual[key], value, label + "." + key, rtol, atol)
    elif expected is None:
        if actual is not None:
            raise ValueError("Unexpected defined value: " + label)
    elif isinstance(expected, (float, list, np.ndarray)):
        if np.shape(actual) != np.shape(expected) or not np.allclose(
            actual, expected, rtol=rtol, atol=atol
        ):
            raise ValueError("Numerical verification failed: " + label)
    elif actual != expected:
        raise ValueError("Discrete verification failed: " + label)


def verify_reconstruction_numerics(items):
    """Independent NumPy SVD, executed on a remote worker by the caller."""
    import numpy as np

    maxima = dict(
        training_mean=0.0,
        person_constant_rmse=0.0,
        rmse_k0_to_4=0.0,
        paired_loss_difference=0.0,
    )
    for request, saved in items:
        y = np.asarray(request["data"]["y"], float)
        tr, te = np.asarray(request["train"]), np.asarray(request["test"])
        if set(tr) & set(te) or sorted(list(tr) + list(te)) != list(range(len(y))):
            raise ValueError("Subject leakage or incomplete fold")
        if saved["train_rows"] != tr.tolist() or saved["test_rows"] != te.tolist():
            raise ValueError("Saved fold differs from frozen fold")
        weights = np.ones(y.shape[1])
        weights[[0, -1]] = 0.5
        mean = y[tr].mean(axis=0)
        _, _, vt = np.linalg.svd((y[tr] - mean) * np.sqrt(weights), full_matrices=False)
        centered = (y[te] - mean) * np.sqrt(weights)
        constant = (y[te] @ weights) / weights.sum()
        baseline = np.sqrt(((y[te] - constant[:, None]) ** 2 @ weights) / weights.sum())
        errors = []
        for k in range(5):
            residual = centered if k == 0 else centered - (centered @ vt[:k].T) @ vt[:k]
            errors.append(np.sqrt((residual**2).sum(axis=1) / weights.sum()))
        errors = np.array(errors).T
        values = dict(
            training_mean=mean,
            person_constant_rmse=baseline,
            rmse_k0_to_4=errors,
            paired_loss_difference=errors - baseline[:, None],
        )
        for key, expected in values.items():
            actual = np.asarray(saved[key], float)
            if actual.shape != expected.shape or not np.allclose(
                actual, expected, rtol=1e-8, atol=1e-9
            ):
                raise ValueError("Independent heldout reconstruction mismatch: " + key)
            maxima[key] = max(maxima[key], float(np.max(np.abs(actual - expected))))
    return dict(status="PASS", folds=len(items), max_absolute_difference=maxima)


def portable_reconstruction_checker():
    # Avoid a scheduler/worker import of this local audit CLI. The worker
    # function imports NumPy inside its body and has no project globals.
    from types import FunctionType

    return FunctionType(
        verify_reconstruction_numerics.__code__,
        {"__builtins__": __builtins__, "__name__": "__main__"},
        "independent_reconstruction_checker",
    )


def verify(run, output, partial=False, scheduler="tcp://192.0.2.54:8786"):
    if output.is_relative_to(ROOT):
        raise ValueError("Private verification output must stay outside the repository")
    frozen = json.loads((run / "run_manifest.json").read_bytes())
    config = frozen["config"]
    data = json.loads((run / "private_inputs/data.json").read_bytes())
    if sha_bytes(canonical(config)) != frozen["config_sha256"]:
        raise ValueError("Config hash mismatch")
    for name, h in frozen["snapshot_sha256"].items():
        if sha(run / "snapshot" / name) != h:
            raise ValueError("Snapshot changed: " + name)
    for name, h in frozen["input_sha256"].items():
        if sha(ROOT / name) != h:
            raise ValueError("Input changed: " + name)
    if sha(run / "private_inputs/data.json") != frozen["private_data_sha256"]:
        raise ValueError("Private input changed")
    if (
        sha(run / "private_inputs/people_private.csv")
        != frozen["input_sha256"][config["source"]["path"]]
    ):
        raise ValueError("Private source copy changed")
    source = pd.read_csv(
        run / "private_inputs/people_private.csv", dtype=str, keep_default_na=False
    )
    source = source.sort_values("ID").reset_index(drop=True)
    if source.ID.duplicated().any() or len(source) != config["expected_people"]:
        raise ValueError("Person frame mismatch")
    values, _ = tokens_to_arrays(
        source[[f"VAS_{m}min" for m in range(1, 21)]].to_numpy()
    )
    for end in config["complete"]["intervals"]:
        complete = np.flatnonzero(np.isfinite(values[:, :end]).all(axis=1))
        observed = np.flatnonzero(np.isfinite(values[:, :end]).any(axis=1))
        expected = dict(
            n_people=len(complete),
            y=values[complete, :end].tolist(),
            long=long_rows(values, complete, end),
        )
        if expected != data["complete" + str(end)]:
            raise ValueError("Complete input frame mismatch")
        frame = data["observed" + str(end)]
        if frame["n_people"] != len(observed) or frame["long"] != long_rows(
            values, observed, end
        ):
            raise ValueError("Actual-minute observed frame mismatch")
        for i, row in enumerate(observed):
            ix = np.flatnonzero(np.isfinite(values[row, :end]))
            if (
                frame["Ly"][i] != values[row, ix].tolist()
                or frame["Lt"][i] != (ix + 1).tolist()
            ):
                raise ValueError("Sparse input filled or reordered")
    if jobs(config) != frozen["jobs"]:
        raise ValueError("Frozen roster mismatch")
    roster = {j["id"]: j for j in frozen["jobs"]}
    records = recover(run)
    if not partial and set(records) != set(roster):
        raise ValueError("Incomplete queue; use --partial for progress audit")
    counts = collections.Counter()
    cells = {}
    cv_items = []
    warnings = []
    peak = 0
    for task, envelope in records.items():
        p = envelope["payload"]
        job = roster[task]
        stage = job["stage"]
        result = p["result"]
        counts[stage] += 1
        request = request_for(config, data, job)
        if (
            p["job"] != job
            or p["config_sha256"] != frozen["config_sha256"]
            or p["input_sha256"] != frozen["private_data_sha256"]
        ):
            raise ValueError("Checkpoint input/config identity mismatch")
        if (
            p["request_sha256"] != sha_bytes(canonical(request))
            or result["task"] != task
        ):
            raise ValueError("Checkpoint request identity mismatch")
        if (
            result["R_version"] != config["runtime"]["R_version"]
            or result["library_paths"][0] != config["runtime"]["library"]
        ):
            raise ValueError("R environment mismatch")
        peak = max(peak, envelope["execution"]["peak_sampled_R_RSS"])
        if peak > config["runtime"]["subprocess_rss_limit_bytes"]:
            raise ValueError("Published task exceeded RSS limit")
        if result.get("warnings"):
            warnings.append(dict(task=task, warnings=result["warnings"]))
        module = job["cell"]["module"]
        frame = data[job["cell"]["frame"]]
        if module == "gamm":
            people = sorted(set(frame["long"]["person"]))
            times = {person: [] for person in people}
            for person, minute in zip(frame["long"]["person"], frame["long"]["time"]):
                times[person].append(minute)
            support = np.asarray([len(times[p]) for p in people])
            adjacent = np.asarray(
                [np.sum(np.diff(sorted(times[p])) == 1) for p in people]
            )
            fits = [result] if stage == "reference" else result.get("replicates", [])
            for i, fit in enumerate(fits):
                if fit["status"] != "estimated":
                    continue
                draw = (
                    np.arange(len(people))
                    if stage == "reference"
                    else np.asarray(request["draws"][i])
                )
                numeric_equal(
                    fit["diagnostics"],
                    dict(
                        n_people=len(draw),
                        n_observations=int(support[draw].sum()),
                        residual_adjacent_pairs=int(adjacent[draw].sum()),
                    ),
                    task + ".support",
                )
                if (
                    len(fit["curve"]) != job["cell"]["end"]
                    or not np.isfinite(fit["curve"]).all()
                ):
                    raise ValueError("Invalid estimated curve")
            if stage == "reference":
                minutes = np.asarray(frame["long"]["time"])
                scores = np.asarray(frame["long"]["vas"])
                numeric_equal(
                    result["empirical_mean"],
                    [scores[minutes == m].mean() for m in request["grid"]],
                    task + ".observed_mean",
                )
        if stage == "reference" and module == "complete":
            y = np.asarray(frame["y"])
            weights = np.ones(y.shape[1])
            weights[[0, -1]] = 0.5
            phi = np.asarray(result["phi"])
            mean = y.mean(axis=0)
            numeric_equal(result["mean"], mean, task + ".mean", rtol=1e-8, atol=1e-9)
            numeric_equal(
                phi.T @ (weights[:, None] * phi),
                np.eye(4),
                task + ".weighted_orthogonality",
                rtol=1e-8,
                atol=1e-9,
            )
            total = float((((y - mean) ** 2) * weights).sum() / (len(y) - 1))
            numeric_equal(
                result["fve"],
                np.asarray(result["eigenvalue"]) / total,
                task + ".full_variance_denominator",
                rtol=1e-8,
                atol=1e-9,
            )
        if stage == "reference" and module == "sparse":
            requested = dict(
                config["sparse"]["options"],
                userBwMu=job["cell"]["bandwidth"][0],
                userBwCov=job["cell"]["bandwidth"][1],
            )
            # fdapace disables FVE selection when methodSelectK is fixed numeric K.
            requested["FVEthreshold"] = 1
            numeric_equal(result["actual_options"], requested, task + ".actual_options")
            if np.shape(result["phi"]) != (config["sparse"]["options"]["nRegGrid"], 4):
                raise ValueError("Sparse reference grid/component count changed")
        if stage in ["gamm", "complete", "sparse"]:
            n = job["stop"] - job["start"]
            reps = (
                result["replicates"]
                if result["status"] == "batch_completed"
                else [result] * n
            )
            if len(reps) != n:
                raise ValueError("Missing replicate")
            cell = cells.setdefault(
                (stage, job["cell"]["id"]), dict(job["cell"], replicates=[], indices=[])
            )
            cell["replicates"].extend(reps)
            cell["indices"].extend(range(job["start"], job["stop"]))
        elif stage == "reconstruction" and result["status"] == "estimated":
            cv_items.append((request, result))
        elif stage == "reference" and result["status"] != "estimated":
            raise ValueError("Reference estimator inestimable")
    report = dict(
        status="PARTIAL_VERIFIED" if partial else "COMPLETED_QUEUE_VERIFIED",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        run_directory=str(run),
        verifier_sha256=sha(Path(__file__)),
        config_sha256=frozen["config_sha256"],
        checkpoints=len(records),
        total_jobs=len(roster),
        stage_counts=dict(counts),
        source_snapshot_checkpoint_request_hashes="PASS",
        private_input_actual_minutes_missingness="PASS",
        warnings=warnings,
        peak_sampled_R_RSS=peak,
        cells=[],
        primary_p_q=None,
        sealed_people_used=0,
    )
    for (stage, cid), cell in sorted(cells.items()):
        reps = cell["replicates"]
        ok = [r for r in reps if r["status"] == "estimated"]
        failures = collections.Counter(
            r.get("reason", "unknown") for r in reps if r["status"] != "estimated"
        )
        row = dict(
            stage=stage,
            cell=cid,
            attempted=len(reps),
            successful=len(ok),
            failed=len(reps) - len(ok),
            failure_reasons=dict(failures),
        )
        if len(cell["indices"]) != len(set(cell["indices"])):
            raise ValueError("Repeated logical replicate index")
        if stage == "gamm":
            row.update(
                apVar_failed=sum(not r["diagnostics"]["apVar_ok"] for r in ok),
                correlation_boundary=sum(
                    bool(r["diagnostics"]["correlation_boundary"]) for r in ok
                ),
                out_of_scale_fits=sum(
                    r["diagnostics"]["fitted_out_of_0_10"] > 0 for r in ok
                ),
            )
        if not partial:
            if sorted(cell["indices"]) != list(range(config[stage]["replicates"])):
                raise ValueError("Logical replicate coverage mismatch")
            summary = json.loads((run / (stage + "_summary.json")).read_bytes())
            subset = [s for s in summary if s["cell"] == cid]
            metrics = (
                [("curve", cell["end"], [None, None], config["MC"]["VAS_absolute"])]
                if stage == "gamm"
                else [
                    ("cumulative_fve", 4, [0, 1], config["MC"]["proportion_absolute"]),
                    ("angle_deg", 4, [0, 90], config["MC"]["angle_absolute_degrees"]),
                ]
            )
            if stage == "complete":
                metrics.append(
                    ("matched_inner", 4, [0, 1], config["MC"]["matched_inner_absolute"])
                )
            if len(subset) != sum(m[1] for m in metrics):
                raise ValueError("Missing or duplicate MC statistic")
            met = 0
            gate = len(ok) > 0 and len(ok) >= config[stage].get(
                "minimum_success_fraction", 0
            ) * len(reps)
            for metric, columns, bounds, absolute in metrics:
                for column in range(columns):
                    saved = next(
                        s
                        for s in subset
                        if s["metric"] == metric and s["index"] == column + 1
                    )
                    numeric_equal(
                        saved,
                        dict(
                            attempted=len(reps),
                            failed=len(reps) - len(ok),
                            failure_reasons=dict(failures),
                        ),
                        cid,
                    )
                    expected = (
                        independently_summarize(
                            [r[metric][column] for r in ok],
                            config["MC"]["total_error_per_module"]
                            / (2 * config["MC"]["families"][stage]),
                            bounds,
                        )
                        if ok
                        else None
                    )
                    if expected:
                        half = expected["MC_max_endpoint_half_width"]
                        width = expected["empirical_range_width"]
                        precise = (
                            half is not None
                            and half <= absolute
                            and (
                                half <= config["MC"]["relative_tolerance"] * width
                                if width
                                else half == 0
                            )
                        )
                        if not gate:
                            expected["lower"] = None
                            expected["upper"] = None
                        numeric_equal(
                            saved, expected, cid + "." + metric + str(column + 1)
                        )
                    else:
                        precise = False
                    numeric_equal(
                        saved["status"],
                        "MC_PRECISION_MET" if precise else "MC_PRECISION_INSUFFICIENT",
                        cid,
                    )
                    numeric_equal(
                        saved["publication"],
                        "success_conditional_descriptive_range"
                        if gate
                        else "WITHHELD_FAILURE_GATE",
                        cid,
                    )
                    if saved["primary_p"] is not None or saved["primary_q"] is not None:
                        raise ValueError("Unexpected primary inference")
                    met += precise
            row.update(
                MC_precision_met=met,
                MC_statistics=len(subset),
                publication_gate_passed=gate,
            )
        report["cells"].append(row)
    if not partial:
        from distributed import Client

        checker = portable_reconstruction_checker()
        # Independent numeric verification uses idle Windows compute nodes.
        with Client(scheduler, set_as_default=False) as client:
            workers = [
                a
                for a, w in client.scheduler_info()["workers"].items()
                if a.startswith("tcp://192.0.2.186:") and w["nthreads"] == 1
            ]
            idle = [a for a in workers if not client.processing(workers=workers)[a]][:8]
            if not idle:
                raise RuntimeError(
                    "No idle remote worker for independent reconstruction checks"
                )
            futures = [
                client.submit(
                    checker,
                    cv_items[i :: len(idle)],
                    workers=[w],
                    allow_other_workers=False,
                    pure=False,
                    retries=0,
                )
                for i, w in enumerate(idle)
            ]
            report["independent_reconstruction_numerics"] = client.gather(futures)
            for f in futures:
                f.release()
        summaries = json.loads((run / "reconstruction_summary.json").read_bytes())
        for cell in summaries:
            selected = [
                r["payload"]
                for r in records.values()
                if r["payload"]["job"]["stage"] == "reconstruction"
                and r["payload"]["job"]["cell"]["id"] == cell["cell"]
            ]
            rows = []
            failures = 0
            for repeat in range(config["complete"]["reconstruction"]["repeats"]):
                folds = [p for p in selected if p["job"]["repeat"] == repeat]
                if len(folds) != config["complete"]["reconstruction"]["folds"]:
                    raise ValueError("Missing reconstruction fold")
                if any(p["result"]["status"] != "estimated" for p in folds):
                    failures += 1
                    continue
                errors = np.concatenate([p["result"]["rmse_k0_to_4"] for p in folds])
                baseline = np.concatenate(
                    [p["result"]["person_constant_rmse"] for p in folds]
                )
                seen = sum([p["result"]["test_rows"] for p in folds], [])
                if sorted(seen) != list(
                    range(data["complete" + cell["cell"][1:]]["n_people"])
                ):
                    raise ValueError("Incomplete whole-person OOF coverage")
                rows.append(
                    dict(
                        repeat=repeat,
                        mean_rmse=errors.mean(axis=0).tolist(),
                        person_constant_rmse=float(baseline.mean()),
                        paired_difference=(errors - baseline[:, None])
                        .mean(axis=0)
                        .tolist(),
                    )
                )
            if len(rows) != len(cell["complete_repeats"]):
                raise ValueError("Completed reconstruction repeat count mismatch")
            for actual, expected in zip(cell["complete_repeats"], rows):
                numeric_equal(actual, expected, cell["cell"])
            numeric_equal(cell["failed_or_incomplete_repeats"], failures, cell["cell"])
        completion = json.loads((run / "completion.json").read_bytes())
        if (
            completion["jobs"] != len(roster)
            or completion["sealed_people_used"] != 0
            or completion["primary_p_q"] is not None
        ):
            raise ValueError("Completion state mismatch")
        for name, h in completion["outputs_sha256"].items():
            if sha(run / name) != h:
                raise ValueError("Completed output changed: " + name)
        report["completed_output_hashes"] = "PASS"
    write_new(output, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--partial", action="store_true")
    parser.add_argument("--scheduler", default="tcp://192.0.2.54:8786")
    args = parser.parse_args()
    result = verify(
        args.run.resolve(), args.output.resolve(), args.partial, args.scheduler
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ["warnings", "independent_reconstruction_numerics"]
            },
            ensure_ascii=False,
        )
    )
