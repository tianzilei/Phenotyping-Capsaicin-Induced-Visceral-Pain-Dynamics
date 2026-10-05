"""Explicitly unvalidated candidate effects, with person bootstrap and full disposition."""

import sys
import json
import uuid
from pathlib import Path
import numpy as np
import pandas as pd
from prepare_reanalysis_20260926 import ROOT, read, write, dump, sha


def prepare(d, standardize=False):
    d = d.copy()
    d["value"] = pd.to_numeric(d["value"], errors="coerce")
    d["vas_mean"] = pd.to_numeric(d["vas_mean"], errors="coerce")
    d = d[np.isfinite(d.value) & np.isfinite(d.vas_mean)]
    if d.duplicated(["person_id", "block"]).any():
        raise ValueError("duplicate person block")
    counts = d.groupby("person_id").block.nunique()
    d = d[d.person_id.isin(counts[counts >= 2].index)]
    if standardize:
        sd = d.groupby("person_id").value.transform("std")
        mean = d.groupby("person_id").value.transform("mean")
        d["value"] = (d.value - mean) / sd
        d = d[np.isfinite(d.value)]
    if len(d) < 5:
        return None, d
    people = sorted(d.person_id.unique())
    g = pd.Categorical(d.person_id, categories=people).codes
    x = d.vas_mean.to_numpy(float)
    y = d.value.to_numpy(float)
    z = pd.get_dummies(d.block.astype(int), drop_first=True).to_numpy(float)
    design = np.column_stack([x, y, z])
    design -= pd.DataFrame(design).groupby(g).transform("mean").to_numpy()
    return (design, g, len(people)), d


def coefficient(prepared, counts=None):
    if prepared is None:
        return None
    a, g, n = prepared
    w = np.ones(len(a)) if counts is None else counts[g]
    x = a[:, 0]
    y = a[:, 1]
    z = a[:, 2:]
    if w.sum() < 5:
        return None
    if z.shape[1]:
        gram = z.T @ (w[:, None] * z)
        if np.linalg.matrix_rank(gram) < z.shape[1]:
            return None
        x = x - z @ np.linalg.solve(gram, z.T @ (w * x))
        y = y - z @ np.linalg.solve(gram, z.T @ (w * y))
    denominator = np.sum(w * x * x)
    if denominator < 1e-10:
        return None
    return float(np.sum(w * x * y) / denominator)


def main():
    run = Path(sys.argv[1]).resolve()
    ecg = Path(sys.argv[2]).resolve()
    hb = Path(sys.argv[3]).resolve()
    out = run / ("candidate_associations_" + uuid.uuid4().hex[:8])
    out.mkdir()
    cp = ROOT / "config/candidate_association_20260926_v1.json"
    cfg = json.loads(cp.read_text(encoding="utf-8"))
    (out / "frozen_config.json").write_bytes(cp.read_bytes())
    # Only this nominal mask rule enters comparisons; all scenarios remain labelled unvalidated.
    e = pd.read_csv(ecg / "features_private.csv", low_memory=False)
    h = pd.read_csv(hb / "features_private.csv", low_memory=False)
    e = e[
        e.metric.isin(["HR", "candidate_RR_RMSSD"])
        & (e.algorithm_candidate_pass == True)
    ].copy()
    e["roi"] = "ECG"
    h = h[
        (h.mad == 6)
        & (h.guard_s == 2)
        & (h.coverage_threshold == 0.9)
        & (h.roi_fraction == 0.5)
        & (h.algorithm_candidate_pass == True)
    ].copy()
    roster = sorted(
        {
            r["roi_label"]
            for r in read(
                ROOT
                / "00_protocol/acquisition_qc_20260919/data/16_fnirs_channel_qc.csv"
            )
            if r["roi_label"]
        }
    )
    table = []
    scenarios = []
    inputs = []
    rng = np.random.default_rng(cfg["bootstrap_seed"])
    targets = [("ECG", "HR"), ("ECG", "candidate_RR_RMSSD")] + [
        (roi, metric) for roi in roster for metric in ["HbO", "HbR"]
    ]
    for roi, metric in targets:
        data = e if roi == "ECG" else h
        target = data[(data.roi == roi) & (data.metric == metric)]
        result = dict(
            roi=roi,
            metric=metric,
            primary_status="not_independently_validated",
            p=None,
            q_BY_n24=None,
            q_BH_n24=None,
            unit="bpm/VAS"
            if metric == "HR"
            else "candidate_RR_ms/VAS"
            if roi == "ECG"
            else "within_person_block_SD/VAS",
        )
        nominal = target[
            (target.support_spec == "A")
            & (target.offset_s == 0)
            & (target.drift_ppm == 0)
        ]
        prepared, d = prepare(nominal, standardize=roi != "ECG")
        beta = coefficient(prepared)
        result.update(
            n_people=d.person_id.nunique(), n_blocks=len(d), candidate_beta=beta
        )
        if beta is not None:
            n = prepared[2]
            values = []
            for _ in range(cfg["bootstrap_replicates"]):
                weights = np.bincount(rng.integers(n, size=n), minlength=n)
                b = coefficient(prepared, weights)
                if b is not None:
                    values.append(b)
            success = len(values)
            result["bootstrap_success"] = success
            if success >= 0.95 * cfg["bootstrap_replicates"]:
                result["candidate_percentile_low"] = float(np.quantile(values, 0.025))
                result["candidate_percentile_high"] = float(np.quantile(values, 0.975))
            result["candidate_interval_role"] = (
                "unvalidated target descriptive stability; not accepted CI"
            )
            inputs.extend(
                dict(
                    roi=roi,
                    metric=metric,
                    person_id=r.person_id,
                    block=int(r.block),
                    value=r.value,
                    vas_mean=r.vas_mean,
                )
                for r in d.itertuples()
            )
        else:
            result["reason"] = (
                "insufficient_support_or_residual_exposure_variation_or_rank"
            )
        table.append(result)
        for (spec, offset, drift), part in target.groupby(
            ["support_spec", "offset_s", "drift_ppm"]
        ):
            prepared, dd = prepare(part, standardize=roi != "ECG")
            b = coefficient(prepared)
            scenarios.append(
                dict(
                    roi=roi,
                    metric=metric,
                    support_spec=spec,
                    offset_s=offset,
                    drift_ppm=drift,
                    n_people=dd.person_id.nunique(),
                    n_blocks=len(dd),
                    candidate_beta=b,
                    status="unvalidated_timing_scenario_not_verified_synchrony",
                )
            )
        print(roi, metric, "candidate processed", flush=True)
    write(out / "planned_24_disposition.csv", table)
    write(out / "timing_scenarios.csv", scenarios)
    write(out / "model_input_private.csv", inputs)
    # Raw feature perturbations on common keys, separately from changes of inclusion.
    changes = []
    for data in [e, h]:
        for (roi, metric, spec), part in data.groupby(
            ["roi", "metric", "support_spec"]
        ):
            base = part[(part.offset_s == 0) & (part.drift_ppm == 0)][
                ["person_id", "block", "value"]
            ]
            for (offset, drift), alter in part.groupby(["offset_s", "drift_ppm"]):
                merged = base.merge(
                    alter[["person_id", "block", "value"]],
                    on=["person_id", "block"],
                    suffixes=("_base", "_shift"),
                )
                delta = merged.value_shift - merged.value_base
                changes.append(
                    dict(
                        roi=roi,
                        metric=metric,
                        support_spec=spec,
                        offset_s=offset,
                        drift_ppm=drift,
                        n_baseline=len(base),
                        n_scenario=len(alter),
                        n_common=len(merged),
                        median_absolute_change=float(np.median(abs(delta)))
                        if len(delta)
                        else None,
                    )
                )
    write(out / "common_window_feature_sensitivity.csv", changes)
    (out / "execution_script.py").write_bytes(Path(__file__).read_bytes())
    dump(
        out / "manifest.json",
        dict(
            status="completed_candidate_only",
            inputs_sha256={
                str(p): sha(p)
                for p in [cp, ecg / "features_private.csv", hb / "features_private.csv"]
            },
            code_sha256=sha(__file__),
            outputs_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()},
        ),
    )
    print(out, flush=True)


if __name__ == "__main__":
    main()
