"""Independent read-only audit and prediction reduction; no new fitted models."""

import hashlib
import json
from pathlib import Path
import sys
from types import FunctionType
import numpy as np
import pandas as pd
from distributed import Client

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from capsaicin.science_completion import canonical
from capsaicin.distributed_prediction import fold_indices, seed
from verify_dask_R_analysis import independently_summarize, numeric_equal
from run_dask_derivative_development import sha, write_new


def independent_samples(config, stage, prepared, records, samples):
    import hashlib
    import numpy as np

    differences = []
    for record in records:
        hasher = hashlib.sha256()
        for rep in range(record["start"], record["stop"]):
            raw = hashlib.sha256(
                f"{config['master_seed']}|{stage}|{rep}".encode()
            ).digest()
            rng = np.random.default_rng(
                np.random.SeedSequence(np.frombuffer(raw, dtype="<u4").tolist())
            )
            draw = rng.integers(0, config["expected_people"], config["expected_people"])
            hasher.update(draw.astype("<i8").tobytes())
            if rep not in samples:
                continue
            result = []
            if stage == "symptoms":
                for num, den in zip(prepared["numerator"], prepared["denominator"]):
                    d = den[draw].sum()
                    result.append(num[draw].sum() / d if d else np.nan)
            else:
                for support, change, h in zip(
                    prepared["support"], prepared["change"], prepared["h"]
                ):
                    delta = change[draw[support[draw]]]
                    if not len(delta):
                        result.extend([np.nan] * 7)
                        continue
                    mean = float(np.mean(delta))
                    median = float(np.quantile(delta, 0.5, method="inverted_cdf"))
                    result.extend(
                        [
                            mean,
                            median,
                            mean / h,
                            median / h,
                            np.mean(delta > 0),
                            np.mean(delta < 0),
                            np.mean(delta == 0),
                        ]
                    )
            actual = samples[rep]
            expected = np.array(result)
            if not np.allclose(
                actual, expected, rtol=1e-10, atol=1e-10, equal_nan=True
            ):
                raise ValueError("Independent scalar mismatch")
            differences.append(float(np.nanmax(abs(actual - expected))))
        if hasher.hexdigest() != record["subject_indices_sha256"]:
            raise ValueError("Subject stream mismatch")
    return dict(
        batches=len(records),
        samples=len(differences),
        maximum_absolute_difference=max(differences, default=0),
    )


def verify_completion(run, out, client):
    m = json.loads((run / "manifest.json").read_bytes())
    cfg = m["config"]
    assert hashlib.sha256(canonical(cfg)).hexdigest() == m["config_sha256"]
    for name, h in m["input_sha256"].items():
        assert sha(ROOT / name) == h
    for name, h in m["snapshot_sha256"].items():
        assert sha(run / "snapshot" / name) == h
    completion = json.loads((run / "completion.json").read_bytes())
    for name, h in completion["outputs_sha256"].items():
        assert sha(run / name) == h
    records = [
        json.loads(line)
        for line in (run / "checkpoint_journal.jsonl").read_bytes().splitlines()
    ]
    assert len(records) == 400 and len({r["task"] for r in records}) == 400
    samples_at = [0, 1, 999, 1000, 9999, 49999, 99999, 149999, 199998, 199999]
    workers = sorted(
        a
        for a in client.scheduler_info()["workers"]
        if a.startswith("tcp://192.0.2.186:")
    )[:8]
    if not workers or any(client.processing(workers).values()):
        raise ValueError("No idle remote verifier")
    fn = FunctionType(
        independent_samples.__code__,
        {"__builtins__": __builtins__, "__name__": "__main__"},
        "independent_samples",
    )
    report = dict(
        status="PASS",
        run=str(run),
        config_sha256=m["config_sha256"],
        checkpoint_hashes=400,
        MC_statistics=503,
        selection="post-compute deterministic numerical audit, not independent full re-estimation",
        stages={},
    )
    for stage in cfg["sequence"]:
        p = run / "private_inputs" / (stage + ".npz")
        assert sha(p) == m["prepared_sha256"][stage]
        with np.load(p, allow_pickle=False) as f:
            prepared = {k: f[k] for k in f.files}
        roster = sorted(
            [r for r in records if r["stage"] == stage], key=lambda r: r["start"]
        )
        arrays = []
        for i, r in enumerate(roster):
            assert r["start"] == i * 1000 and r["stop"] == (i + 1) * 1000
            p = run / "results" / (r["task"] + ".npz")
            assert sha(p) == r["file_sha256"]
            assert (
                r["config_sha256"] == m["config_sha256"]
                and r["input_sha256"] == m["prepared_sha256"][stage]
            )
            with np.load(p, allow_pickle=False) as f:
                v = f["values"]
            assert (
                list(v.shape) == r["values_shape"]
                and hashlib.sha256(v.astype("<f8").tobytes()).hexdigest()
                == r["logical_values_sha256"]
            )
            arrays.append(v)
        values = np.concatenate(arrays)
        del arrays
        summary = json.loads((run / (stage + "_summary.json")).read_bytes())
        for j, s in enumerate(summary):
            valid = values[:, j][np.isfinite(values[:, j])]
            expected = independently_summarize(
                valid, 0.05 / (len(summary) * 2), s["bounds"]
            )
            numeric_equal(s, expected, stage + "." + str(j))
            met = (
                expected["MC_max_endpoint_half_width"] <= s["absolute_MC_target"]
                and expected["MC_max_endpoint_half_width"]
                <= 0.02 * expected["empirical_range_width"]
            )
            assert s["status"] == (
                "MC_PRECISION_MET" if met else "MC_PRECISION_INSUFFICIENT"
            )
            assert s["valid"] == len(valid) and s["undefined"] == len(values) - len(
                valid
            )
        futures = []
        for i in range(8):
            subset = roster[i::8]
            keys = {
                k: values[k]
                for k in samples_at
                if any(r["start"] <= k < r["stop"] for r in subset)
            }
            futures.append(
                client.submit(
                    fn,
                    cfg,
                    stage,
                    prepared,
                    subset,
                    keys,
                    workers=[workers[i % len(workers)]],
                    pure=False,
                )
            )
        audits = client.gather(futures)
        for f in futures:
            f.release()
        report["stages"][stage] = dict(
            attempted=len(values),
            statistics=len(summary),
            MC_met=sum(s["status"] == "MC_PRECISION_MET" for s in summary),
            undefined=sum(s["undefined"] for s in summary),
            all_subject_streams_verified=sum(x["batches"] for x in audits),
            scalar_samples=sum(x["samples"] for x in audits),
            maximum_absolute_difference=max(
                x["maximum_absolute_difference"] for x in audits
            ),
        )
        del values
    write_new(out / "new_completion_verification.json", report)
    return report


def verify_predictions(run, out):
    m = json.loads((run / "run_manifest.json").read_bytes())
    cfg = m["config"]
    assert hashlib.sha256(canonical(cfg)).hexdigest() == m["config_sha256"]
    for name, h in m["input_sha256"].items():
        assert sha(ROOT / name) == h
    for name, h in m["code_sha256"].items():
        assert sha(run / "snapshot" / name) == h
    completion = json.loads((run / "completion.json").read_bytes())
    for name, h in completion.get("outputs_sha256", {}).items():
        assert sha(run / name) == h
    records = [
        json.loads(line)
        for line in (run / "checkpoint_journal.jsonl").read_bytes().splitlines()
    ]
    assert len(records) == 200 and len({r["task"] for r in records}) == 200
    payloads = {}
    for r in records:
        p = run / "results" / (r["task"] + ".json")
        assert sha(p) == r["file_sha256"]
        envelope = json.loads(p.read_bytes())
        p = envelope["payload"]
        assert hashlib.sha256(canonical(p)).hexdigest() == envelope["payload_sha256"]
        assert (
            p["config_sha256"] == m["config_sha256"]
            and p["input_sha256"] == cfg["prepared_input_sha256"][p["stage"]]
        )
        payloads[p["stage"], p["repeat"], p["fold"]] = p
    rows = []
    for stage in cfg["sequence"]:
        input_path = run / "private_inputs" / (stage + ".npz")
        assert sha(input_path) == cfg["prepared_input_sha256"][stage]
        with np.load(input_path, allow_pickle=False) as f:
            prepared = tuple(f["a" + str(i)] for i in range(4))
        x, y, groups, minutes = prepared
        people = np.unique(groups)
        old = json.loads((run / (stage + "_repeat_summaries.json")).read_bytes())
        for repeat in range(20):
            predictions = np.full((len(y), 3), np.nan)
            coverage = np.zeros(len(y), int)
            for fold in range(5):
                p = payloads[stage, repeat, fold]
                train, test, inner = fold_indices(cfg, prepared, stage, repeat, fold)
                assert (
                    p["test_row_indices"] == test.tolist()
                    and p["n_train_people"] == len(np.unique(groups[train]))
                    and p["n_test_people"] == len(np.unique(groups[test]))
                )
                assert (
                    p["observed"] == y[test].tolist()
                    and p["test_person_indices"] == groups[test].tolist()
                    and p["time_min"] == minutes[test].tolist()
                )
                assert p["inner_person_disjoint"] and p["outer_person_disjoint"]
                for purpose in ["outer", "inner", "forest"]:
                    assert p[purpose + "_seed"] == seed(
                        cfg,
                        stage,
                        repeat,
                        purpose,
                        None if purpose == "outer" else fold,
                    )
                a = np.asarray(p["predictions"])
                assert a.shape == (len(test), 3) and np.isfinite(a).all()
                assert np.array_equal(
                    a[:, 0], x[test, 2 if stage == "next_rating" else 4]
                )
                predictions[test] = a
                coverage[test] += 1
            assert np.all(coverage == 1)
            absolute = abs(predictions - y[:, None])
            squared = (predictions - y[:, None]) ** 2
            for weighting in ["window_equal", "person_equal"]:
                if weighting == "window_equal":
                    mae = absolute.mean(axis=0)
                    rmse = np.sqrt(squared.mean(axis=0))
                else:
                    mae = np.mean(
                        [absolute[groups == g].mean(axis=0) for g in people], axis=0
                    )
                    rmse = np.sqrt(
                        np.mean(
                            [squared[groups == g].mean(axis=0) for g in people], axis=0
                        )
                    )
                metrics = {
                    metric + "_" + model: float(v)
                    for metric, arr in [("MAE", mae), ("RMSE", rmse)]
                    for model, v in zip(cfg["models"], arr)
                }
                metrics.update(
                    {
                        metric + "_" + model + "_minus_last_value": float(
                            arr[i] - arr[0]
                        )
                        for metric, arr in [("MAE", mae), ("RMSE", rmse)]
                        for i, model in enumerate(cfg["models"])
                        if i
                    }
                )
                numeric_equal(
                    old[repeat][weighting], metrics, stage + ".repeat" + str(repeat)
                )
                for metric, value in metrics.items():
                    rows.append(
                        dict(
                            task=stage,
                            repeat=repeat,
                            weighting=weighting,
                            metric=metric,
                            value=value,
                            people=len(people),
                            target_rows=len(y),
                        )
                    )
    frame = pd.DataFrame(rows)
    frame.to_csv(out / "prediction_all_repeat_metrics.csv", index=False)
    aggregate = (
        frame.groupby(["task", "weighting", "metric"], sort=False)
        .value.agg(["median", "min", "max"])
        .reset_index()
    )
    aggregate.to_csv(out / "prediction_summary.csv", index=False)
    report = dict(
        status="PASS",
        run=str(run),
        checkpoints=200,
        whole_person_outer_inner_partitions="PASS",
        OOF_coverage_targets_times_persistence="PASS",
        independent_all_20_repeat_metrics_both_weights="PASS",
        new_model_fits=0,
        role="internal partition/training sensitivity; min/max not CI; no sealed/external validation",
        summary=aggregate.to_dict("records"),
    )
    write_new(out / "prediction_verification.json", report)
    return report


if __name__ == "__main__":
    base = Path.home() / ".local/share/capsaicin-dask"
    out = base / "audit/scientific_completion_20261004_v1"
    out.mkdir(parents=True, exist_ok=False)
    with Client("tcp://192.0.2.54:8786", set_as_default=False) as client:
        a = verify_completion(
            base / "runs/science_completion_20261003T180414Z_fc7855a4", out, client
        )
        print(json.dumps(a), flush=True)
    b = verify_predictions(
        base / "runs/dask_prediction_repeats_20261003T105043Z_8eaf27a2", out
    )
    print(
        json.dumps(dict(prediction_status=b["status"], checkpoints=b["checkpoints"])),
        flush=True,
    )
    write_new(
        out / "manifest.json",
        dict(
            verifier_sha256=sha(Path(__file__)),
            outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
        ),
    )
